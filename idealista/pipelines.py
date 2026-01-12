import json
import os
import requests
from itemadapter import ItemAdapter

class DuplicatesPipeline:
    def __init__(self):
        self.history_file = "history.json"
        self.history = set()

    def open_spider(self, spider):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    self.history = set(data)
                spider.logger.info(f"Loaded {len(self.history)} items from history.")
            except (json.JSONDecodeError, IOError):
                self.history = set()
        else:
            self.history = set()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if adapter["id"] in self.history:
            # We silently drop it or explicitly drop. 
            # Scrapy DropItem exception stops processing.
            from scrapy.exceptions import DropItem
            raise DropItem(f"Duplicate item found: {adapter['id']}")
        else:
            self.history.add(adapter["id"])
            return item

    def close_spider(self, spider):
        # Save history
        with open(self.history_file, "w") as f:
            json.dump(list(self.history), f, indent=2)
        spider.logger.info(f"Saved {len(self.history)} items to history.")


class TelegramPipeline:
    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        
        token = spider.settings.get("TELEGRAM_TOKEN")
        chat_id = spider.settings.get("TELEGRAM_CHAT_ID")
        
        if not token or not chat_id:
            spider.logger.warning("Telegram credentials not found. Skipping notification.")
            return item

        msg = (
            f"🏠 *New Listing*\n\n"
            f"*{adapter['title']}*\n"
            f"💰 {adapter['price']}\n"
            f"🔗 [View Listing]({adapter['link']})"
        )

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                spider.logger.error(f"Telegram Error: {response.text}")
            else:
                spider.logger.info(f"Sent Telegram notification for {adapter['id']}")
        except Exception as e:
            spider.logger.error(f"Failed to send Telegram message: {e}")

        return item
