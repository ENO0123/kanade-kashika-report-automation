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
import google.genai as genai


class ReportSender:
    def __init__(self, looker_studio_url: str, slack_token: str, slack_channel: str, 
                 gemini_api_key: str = None, enable_ai_analysis: bool = True):
        self.looker_studio_url = looker_studio_url
        self.slack_client = WebClient(token=slack_token)
        self.slack_channel = slack_channel
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        self.enable_ai_analysis = enable_ai_analysis
        
        # Gemini APIの設定
        if enable_ai_analysis and gemini_api_key:
            self.gemini_client = genai.Client(api_key=gemini_api_key)
        else:
            self.gemini_client = None
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
        chrome_options.add_argument("--disable-extensions")
        
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
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    
    def export_pdf_from_looker_studio(self) -> Path:
        """Looker StudioからPDFをエクスポート"""
        driver = None
        try:
            print(f"Looker Studioにアクセス中: {self.looker_studio_url}")
            driver = self.setup_driver()
            driver.get(self.looker_studio_url)
            
            print("ページの読み込みを待機中...")
            time.sleep(10)
            
            try:
                WebDriverWait(driver, 60).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                print("警告: タイムアウトしましたが、続行します...")
            
            print("レポートのレンダリングを待機中...")
            time.sleep(15)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_path = self.output_dir / f"report_{timestamp}.pdf"
            
            print("PDFを生成中...")
            result = driver.execute_cdp_cmd("Page.printToPDF", {
                "printBackground": True,
                "paperWidth": 11.69,
                "paperHeight": 8.27,
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.4,
                "marginRight": 0.4
            })
            
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
        """Gemini AIを使用してPDFを解析し、要約コメントを生成"""
        if not self.gemini_client:
            return None
        
        try:
            print("🤖 AIでPDFを解析中...")
            
            prompt = """
このPDFレポートを分析して、以下の観点で日本語で要約してください：
1. レポートの主要な内容・テーマ
2. 重要な数値や指標（あれば）
3. 注目すべきポイントやトレンド
4. 簡潔なまとめ（2-3文程度）

要約は読みやすく、Slackのコメントとして適切な形式で出力してください。
"""
            
            pdf_file = self.gemini_client.files.upload(file=str(pdf_path))
            
            while pdf_file.state.name == "PROCESSING":
                time.sleep(2)
                pdf_file = self.gemini_client.files.get(name=pdf_file.name)
            
            if pdf_file.state.name == "FAILED":
                raise Exception(f"ファイルのアップロードに失敗しました: {pdf_file.state.name}")
            
            response = self.gemini_client.models.generate_content(
                model='gemini-1.5-pro',
                contents=[prompt, pdf_file]
            )
            
            analysis = response.text
            print("✅ AI解析が完了しました")
            
            try:
                self.gemini_client.files.delete(name=pdf_file.name)
            except Exception as e:
                print(f"⚠️  ファイルの削除中にエラーが発生しました（無視します）: {str(e)}")
            
            return analysis
            
        except Exception as e:
            print(f"⚠️  AI解析中にエラーが発生しました: {str(e)}")
            return None
    
    def send_to_slack(self, pdf_path: Path, message: str = None, ai_comment: str = None):
        """PDFをSlackに送信"""
        try:
            if message is None:
                message = f"📊 Looker Studioレポート - {datetime.now().strftime('%Y年%m月%d日 %H:%M')}"
            
            if ai_comment:
                message += f"\n\n🤖 **AI解析結果:**\n{ai_comment}"
            
            print(f"Slackに送信中: {self.slack_channel}")
            
            channel_param = self.slack_channel.strip()
            
            response = self.slack_client.files_upload_v2(
                channel=channel_param,
                file=str(pdf_path),
                filename=pdf_path.name,
                title=pdf_path.stem,
                initial_comment=message
            )
            
            print(f"✅ Slackに送信しました: {response['files'][0]['name']}")
            
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
            
            pdf_path = self.export_pdf_from_looker_studio()
            
            ai_comment = None
            if self.enable_ai_analysis and self.gemini_client:
                ai_comment = self.analyze_pdf_with_ai(pdf_path)
            
            self.send_to_slack(pdf_path, ai_comment=ai_comment)
            
            print("=" * 50)
            print("処理が完了しました")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ 処理中にエラーが発生しました: {str(e)}")
            sys.exit(1)


def main():
    """メイン関数"""
    looker_studio_url = os.getenv("LOOKER_STUDIO_URL")
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    slack_channel = os.getenv("SLACK_CHANNEL")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    enable_ai_analysis = os.getenv("ENABLE_AI_ANALYSIS", "true").lower() == "true"
    
    if not looker_studio_url:
        print("❌ エラー: LOOKER_STUDIO_URL環境変数が設定されていません")
        sys.exit(1)
    
    if not slack_token:
        print("❌ エラー: SLACK_BOT_TOKEN環境変数が設定されていません")
        sys.exit(1)
    
    if not slack_channel:
        print("❌ エラー: SLACK_CHANNEL環境変数が設定されていません")
        sys.exit(1)
    
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
