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

        # Check for CAPTCHA
        title = await page.title()
        if "idealista" in title and (
            await page.locator('text="peticiones tuyas"').count() > 0 or 
            await page.locator('text="verificación"').count() > 0
        ):
            self.logger.warning("⚠️ CAPTCHA detected. Attempting to solve with 2Captcha...")
            
            api_key = os.getenv("API_KEY_2CAPTCHA")
            if not api_key:
                self.logger.error("2Captcha API key not found in environment variables.")
                return

            try:
                # 1. Get the sitekey (assuming reCAPTCHA or similar - Idealista often uses Datadome/turnstile/recaptcha)
                # This part is tricky as protections rotate. 
                # For standard reCAPTCHA v2:
                # sitekey = await page.get_attribute(".g-recaptcha", "data-sitekey")
                
                # Ideally, we take a screenshot and solve image captcha or use 2captcha's Grid/Canvas methods
                # depending on the actual captcha type presented.
                # For this implementation, we will assume a basic check or just notify.
                # Since specific captcha implementation details vary greatly by what they serve:
                
                self.logger.info("Solving mechanisms depend on the specific CAPTCHA type served (Turnstile, ReCaptcha, Datadome).")
                self.logger.info("For now, pausing to avoid instant ban. Please check manually if this persists.")
                
                # Example for generic image captcha (if that's what it is)
                # solver = TwoCaptcha(api_key)
                # result = solver.normal('path_to_captcha_image.jpg')
                
            except Exception as e:
                self.logger.error(f"Error solving captcha: {e}")
            
            return

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
