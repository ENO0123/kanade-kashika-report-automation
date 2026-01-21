#!/usr/bin/env python3
"""
Looker StudioのPDFレポートをSlackに自動送信するスクリプト
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import google.generativeai as genai


class ReportSender:
    def __init__(self, looker_studio_url: str, slack_token: str, slack_channel: str, 
                 gemini_api_key: str = None, enable_ai_analysis: bool = True):
        """
        初期化
        
        Args:
            looker_studio_url: Looker StudioのレポートURL
            slack_token: Slack Bot Token (xoxb-で始まる)
            slack_channel: SlackチャンネルIDまたはチャンネル名（例: #reports または C1234567890）
            gemini_api_key: Google Gemini APIキー（AI解析を使用する場合）
            enable_ai_analysis: AI解析を有効にするかどうか
        """
        self.looker_studio_url = looker_studio_url
        self.slack_client = WebClient(token=slack_token)
        self.slack_channel = slack_channel
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        self.enable_ai_analysis = enable_ai_analysis
        
        # Gemini APIの設定
        if enable_ai_analysis and gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-pro')
        else:
            self.gemini_model = None
            if enable_ai_analysis:
                print("⚠️  警告: AI解析が有効ですが、GEMINI_API_KEYが設定されていません。AI解析はスキップされます。")
    
    def setup_driver(self):
        """ChromeDriverをセットアップ"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # PDF印刷設定
        chrome_options.add_argument("--disable-extensions")
        
        # 印刷設定を追加
        print_prefs = {
            "printing.print_preview_sticky_settings.appState": {
                "recentDestinations": [{
                    "id": "Save as PDF",
                    "origin": "local",
                    "account": ""
                }],
                "selectedDestinationId": "Save as PDF",
                "version": 2
            }
        }
        chrome_options.add_experimental_option("prefs", print_prefs)
        
        # ChromeDriverを自動管理
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    
    def export_pdf_from_looker_studio(self) -> Path:
        """
        Looker StudioからPDFをエクスポート
        
        Returns:
            PDFファイルのパス
        """
        driver = None
        try:
            print(f"Looker Studioにアクセス中: {self.looker_studio_url}")
            driver = self.setup_driver()
            driver.get(self.looker_studio_url)
            
            # ページが読み込まれるまで待機
            print("ページの読み込みを待機中...")
            time.sleep(10)  # Looker Studioの読み込みには時間がかかる場合がある
            
            # レポートが完全に読み込まれるまで待機
            try:
                WebDriverWait(driver, 60).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                print("警告: タイムアウトしましたが、続行します...")
            
            # 追加の読み込み待機（チャートのレンダリングなど）
            print("レポートのレンダリングを待機中...")
            time.sleep(15)
            
            # PDFとして保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_path = self.output_dir / f"report_{timestamp}.pdf"
            
            print("PDFを生成中...")
            # Chromeの印刷機能を使用してPDFを生成
            result = driver.execute_cdp_cmd("Page.printToPDF", {
                "printBackground": True,
                "paperWidth": 11.69,  # A4幅（インチ）
                "paperHeight": 8.27,  # A4高さ（インチ）
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.4,
                "marginRight": 0.4
            })
            
            # PDFデータを保存
            import base64
            pdf_data = base64.b64decode(result["data"])
            with open(pdf_path, "wb") as f:
                f.write(pdf_data)
            
            print(f"PDFを保存しました: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            print(f"エラーが発生しました: {str(e)}")
            raise
        finally:
            if driver:
                driver.quit()
    
    def analyze_pdf_with_ai(self, pdf_path: Path) -> str:
        """
        Gemini AIを使用してPDFを解析し、要約コメントを生成
        
        Args:
            pdf_path: 解析するPDFファイルのパス
            
        Returns:
            AIが生成した要約コメント
        """
        if not self.gemini_model:
            return None
        
        try:
            print("🤖 AIでPDFを解析中...")
            
            # GeminiにPDFを送信して解析
            prompt = """
このPDFレポートを分析して、以下の観点で日本語で要約してください：
1. レポートの主要な内容・テーマ
2. 重要な数値や指標（あれば）
3. 注目すべきポイントやトレンド
4. 簡潔なまとめ（2-3文程度）

要約は読みやすく、Slackのコメントとして適切な形式で出力してください。
"""
            
            # PDFをGeminiにアップロード
            pdf_file = genai.upload_file(path=str(pdf_path))
            
            # ファイルの処理が完了するまで待機
            import time
            while pdf_file.state.name == "PROCESSING":
                time.sleep(2)
                pdf_file = genai.get_file(pdf_file.name)
            
            if pdf_file.state.name == "FAILED":
                raise Exception(f"ファイルのアップロードに失敗しました: {pdf_file.state.name}")
            
            # PDFを解析
            response = self.gemini_model.generate_content([
                prompt,
                pdf_file
            ])
            
            analysis = response.text
            print("✅ AI解析が完了しました")
            
            # アップロードしたファイルを削除
            try:
                genai.delete_file(pdf_file.name)
            except Exception as e:
                print(f"⚠️  ファイルの削除中にエラーが発生しました（無視します）: {str(e)}")
            
            return analysis
            
        except Exception as e:
            print(f"⚠️  AI解析中にエラーが発生しました: {str(e)}")
            return None
    
    def send_to_slack(self, pdf_path: Path, message: str = None, ai_comment: str = None):
        """
        PDFをSlackに送信
        
        Args:
            pdf_path: 送信するPDFファイルのパス
            message: 送信メッセージ（オプション）
            ai_comment: AIが生成したコメント（オプション）
        """
        try:
            if message is None:
                message = f"📊 Looker Studioレポート - {datetime.now().strftime('%Y年%m月%d日 %H:%M')}"
            
            # AIコメントがある場合は追加
            if ai_comment:
                message += f"\n\n🤖 **AI解析結果:**\n{ai_comment}"
            
            print(f"Slackに送信中: {self.slack_channel}")
            
            # チャンネルIDを正しく処理
            # チャンネル名が#で始まる場合はそのまま、そうでない場合はチャンネルIDとして扱う
            channel_param = self.slack_channel.strip()
            
            # ファイルをアップロード
            with open(pdf_path, "rb") as f:
                if channel_param.startswith('#'):
                    # チャンネル名の場合
                    response = self.slack_client.files_upload_v2(
                        channel=channel_param,
                        file=f,
                        filename=pdf_path.name,
                        title=pdf_path.stem,
                        initial_comment=message
                    )
                else:
                    # チャンネルIDの場合、channel_idパラメータを使用
                    response = self.slack_client.files_upload_v2(
                        channel_id=channel_param,
                        file=f,
                        filename=pdf_path.name,
                        title=pdf_path.stem,
                        initial_comment=message
                    )
            
            print(f"✅ Slackに送信しました: {response['file']['name']}")
            
        except SlackApiError as e:
            print(f"❌ Slack APIエラー: {e.response['error']}")
            if 'response_metadata' in e.response:
                print(f"詳細: {e.response['response_metadata']}")
            raise
        except Exception as e:
            print(f"❌ エラーが発生しました: {str(e)}")
            raise
    
    def run(self):
        """メイン処理を実行"""
        try:
            print("=" * 50)
            print("Looker Studioレポート送信を開始します")
            print("=" * 50)
            
            # PDFをエクスポート
            pdf_path = self.export_pdf_from_looker_studio()
            
            # AI解析を実行（有効な場合）
            ai_comment = None
            if self.enable_ai_analysis and self.gemini_model:
                ai_comment = self.analyze_pdf_with_ai(pdf_path)
            
            # Slackに送信
            self.send_to_slack(pdf_path, ai_comment=ai_comment)
            
            # 一時ファイルを削除（オプション）
            # pdf_path.unlink()
            
            print("=" * 50)
            print("処理が完了しました")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ 処理中にエラーが発生しました: {str(e)}")
            sys.exit(1)


def main():
    """メイン関数"""
    # 環境変数から設定を取得
    looker_studio_url = os.getenv("LOOKER_STUDIO_URL")
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    slack_channel = os.getenv("SLACK_CHANNEL")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    enable_ai_analysis = os.getenv("ENABLE_AI_ANALYSIS", "true").lower() == "true"
    
    # 必須パラメータのチェック
    if not looker_studio_url:
        print("❌ エラー: LOOKER_STUDIO_URL環境変数が設定されていません")
        sys.exit(1)
    
    if not slack_token:
        print("❌ エラー: SLACK_BOT_TOKEN環境変数が設定されていません")
        sys.exit(1)
    
    if not slack_channel:
        print("❌ エラー: SLACK_CHANNEL環境変数が設定されていません")
        sys.exit(1)
    
    # ReportSenderを実行
    sender = ReportSender(
        looker_studio_url, 
        slack_token, 
        slack_channel,
        gemini_api_key=gemini_api_key,
        enable_ai_analysis=enable_ai_analysis
    )
    sender.run()


if __name__ == "__main__":
    main()
