import scrapy
import os
from twocaptcha import TwoCaptcha
from scrapy_playwright.page import PageMethod
from idealista.items import IdealistaItem

class SearchSpider(scrapy.Spider):
    name = "search"
    allowed_domains = ["idealista.com"]
    
    # URL from the original script
    start_urls = [
        "https://www.idealista.com/areas/venta-viviendas/con-precio-hasta_150000,precio-desde_80000,pisos,de-tres-dormitorios,de-cuatro-cinco-habitaciones-o-mas,ascensor,garaje,ultimas-plantas,plantas-intermedias/?shape=%28%28wrlnFbknBktKcsOej%40abDz%5CwbSrzPkyNb%7EM%7CuGvjHshPhtJp%7CHuaAdlLezLlnM%7DdAngJisGwv%40_%60M%60%7CQ%29%29&ordenado-por=fecha-publicacion-desc"
    ]

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                meta={
                    "playwright": True,
                    "playwright_include_page": True,
                    "handle_httpstatus_list": [403],
                    "playwright_page_methods": [
                        # Wait for the cookie banner or listing to appear
                        # We try to click the cookie button if it exists, but usually we just want to wait for content
                        # PageMethod("click", "#didomi-notice-agree-button", timeout=5000), 
                        # Ideally simply wait for the content to load
                        PageMethod("wait_for_load_state", "domcontentloaded")
                    ],
                },
            )

    async def parse(self, response):
        page = response.meta["playwright_page"]
        
        # Cookie handling - try to click if visible
        try:
            if await page.is_visible("#didomi-notice-agree-button"):
                await page.click("#didomi-notice-agree-button")
                await page.wait_for_timeout(2000)
        except Exception:
            pass

        # 1. Simple 403 / Title Check
        if response.status == 403:
             self.logger.warning(f"⚠️  Access Denied (HTTP 403). Attempting to solve DataDome CAPTCHA...")
             
             api_key = os.getenv("API_KEY_2CAPTCHA")
             if not api_key:
                 self.logger.error("❌ No API_KEY_2CAPTCHA found. Cannot solve.")
                 return

             # Find the captcha URL from the iframes
             frames = page.frames
             captcha_url = None
             for f in frames:
                 if "geo.captcha-delivery.com" in f.url:
                     captcha_url = f.url
                     break
            
             if not captcha_url:
                 # Backup: check if it's in the content as a script var or basic iframe src
                 content = await page.content()
                 if "geo.captcha-delivery.com" in content:
                     # Attempt to parse or just give up for this simple iteration
                     self.logger.error("❌ Could not isolate DataDome iframe URL from Playwright frames.")
                 return

             self.logger.info(f"🧩 Check found: {captcha_url}")
             
             solver = TwoCaptcha(api_key)
             try:
                 self.logger.info("⏳ Sending to 2Captcha...")
                 # DataDome method requires: pageurl, captcha_url, useragent
                 # 2captcha-python 2.1+ supports grid/datadome. 
                 # We use the 'datadome' method if available or fall back to 'grid' custom.
                 # Actually standard library usage:
                 result = solver.datadome(
                     sitekey=None, # SDK extracts cid from captcha_url usually, or passes url directly
                     captcha_url=captcha_url,
                     pageurl=response.url,
                     userAgent=await page.evaluate("navigator.userAgent"),
                     proxy=None # GitHub Actions is proxies, usually requires proxy but we try.
                 )
                 
                 code = result.get('code') # This is the cookie content usually "datadome=..."
                 if code:
                     self.logger.info(f"✅ CAPTCHA Solved! Cookie: {code[:30]}...")
                     # The result is the value for the 'datadome' cookie
                     cookie_value = code.replace("datadome=", "")
                     
                     await page.context.add_cookies([{
                         "name": "datadome",
                         "value": cookie_value,
                         "domain": ".idealista.com",
                         "path": "/"
                     }])
                     
                     self.logger.info("🔄 Reloading page check content...")
                     await page.reload(wait_until="domcontentloaded")
                     
                     # Re-check title
                     if "idealista" in (await page.title()).lower():
                         self.logger.info("🎉 Access Restored!")
                     else:
                         self.logger.warning("⚠️ Still suspicious after reload.")
                         
             except Exception as e:
                 self.logger.error(f"❌ Solver Error: {e}")
             
             # If we solved it, the page object is updated. 
             # We can proceed to scrape items from the reloaded page.
             # Wait a sec for hydration
             await page.wait_for_timeout(3000)

        # Proceed to scrape (whether strictly 200 or recovered 403)


        # Scrape items
        items = await page.query_selector_all("article.item")
        
        for item in items:
            idealista_item = IdealistaItem()
            
            # Extract ID
            idealista_item["id"] = await item.get_attribute("data-adid")
            
            # Extract Title
            title_el = await item.query_selector(".item-link")
            if title_el:
                idealista_item["title"] = (await title_el.inner_text()).strip()
                href = await title_el.get_attribute("href")
                if href:
                    idealista_item["link"] = f"https://www.idealista.com{href}"
            
            # Extract Price
            price_el = await item.query_selector(".item-price")
            if price_el:
                idealista_item["price"] = (await price_el.inner_text()).strip()

            if idealista_item.get("id") and idealista_item.get("title"):
                yield idealista_item

        # Allow the page to close
        await page.close()
