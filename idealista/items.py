import scrapy

class IdealistaItem(scrapy.Item):
    id = scrapy.Field()
    title = scrapy.Field()
    price = scrapy.Field()
    link = scrapy.Field()
