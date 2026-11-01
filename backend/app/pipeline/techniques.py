"""Curated GEO technique library.

Deliberately hand-maintained instead of auto-scraped from blogs: a small set of
techniques with primary-source references beats a large noisy one. Review it
periodically. Each recommendation links to one of these *and* to observed
evidence from the user's own run.
"""

R = lambda label, url: {"label": label, "url": url, "kind": "reference"}  # noqa: E731

GEO_PAPER = R("GEO: Generative Engine Optimization (Aggarwal et al., 2023)", "https://arxiv.org/abs/2311.09735")
GBP_RANKING = R("Google: Tips to improve your local ranking", "https://support.google.com/business/answer/7091")

TECHNIQUES: dict[str, dict] = {
    "unblock_ai_crawlers": {
        "title": "Allow AI search crawlers in robots.txt",
        "how": "Remove Disallow rules for search-time crawlers (OAI-SearchBot, ChatGPT-User, PerplexityBot, Bingbot). "
               "Blocking training-only bots (GPTBot, Google-Extended) is a separate choice and does not hide you from live answers.",
        "references": [R("OpenAI: Overview of OpenAI crawlers", "https://platform.openai.com/docs/bots"),
                       R("Perplexity: Perplexity crawlers", "https://docs.perplexity.ai/guides/bots")],
    },
    "local_business_schema": {
        "title": "Add LocalBusiness structured data",
        "how": "Add JSON-LD with your exact business name, address, phone, service area, hours and sameAs links to your "
               "Google, Yelp and social profiles. This gives engines an unambiguous entity to match your name to.",
        "references": [R("Google: Local business structured data", "https://developers.google.com/search/docs/appearance/structured-data/local-business"),
                       R("schema.org/LocalBusiness", "https://schema.org/LocalBusiness")],
    },
    "faq_content": {
        "title": "Answer the questions customers ask, on your site",
        "how": "Add an FAQ or Q&A section covering pricing ranges, service area, turnaround, and how you compare. "
               "Engines lift direct, specific answers; include concrete numbers and facts rather than marketing copy.",
        "references": [GEO_PAPER, R("Google: Creating helpful, reliable, people-first content", "https://developers.google.com/search/docs/fundamentals/creating-helpful-content")],
    },
    "content_depth": {
        "title": "Make your service pages substantive",
        "how": "Expand thin pages with specifics: services, equipment, past jobs, statistics, client quotes, service area. "
               "The GEO study found adding statistics, quotations and citations measurably increased visibility in generative answers.",
        "references": [GEO_PAPER],
    },
    "reviews_on_site": {
        "title": "Show reviews and testimonials on your site",
        "how": "Publish real customer reviews (with names and dates where permitted) and link to your Google and Yelp profiles.",
        "references": [GBP_RANKING],
    },
    "sitemap": {
        "title": "Publish an XML sitemap",
        "how": "Generate /sitemap.xml, list it in robots.txt, and submit it in Google Search Console and Bing Webmaster Tools.",
        "references": [R("Google: Learn about sitemaps", "https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview")],
    },
    "meta_description": {
        "title": "Write a descriptive title and meta description",
        "how": "Say what you do and where, e.g. 'LED Wall Rental in Dallas, TX | Acme'. Search-grounded engines read these when choosing sources.",
        "references": [R("Google: Influencing title links", "https://developers.google.com/search/docs/appearance/title-link")],
    },
    "bing_index": {
        "title": "Make sure Bing indexes you",
        "how": "ChatGPT search and Copilot draw heavily on Bing's index. Verify your site in Bing Webmaster Tools, submit your sitemap, "
               "enable IndexNow, and claim your Bing Places listing.",
        "references": [R("Bing Webmaster Tools", "https://www.bing.com/webmasters"), R("IndexNow", "https://www.indexnow.org/"),
                       R("Bing Places for Business", "https://www.bingplaces.com/")],
    },
    "maps_listings": {
        "title": "Complete your Google Business Profile and map listings",
        "how": "Fill every field, pick precise categories, add photos, and keep earning reviews. Gemini grounds on Google Search and Maps data.",
        "references": [GBP_RANKING, R("Apple Business Connect", "https://businessconnect.apple.com/")],
    },
    "review_site_presence": {
        "title": "Get listed and reviewed on the review sites engines cite",
        "how": "Claim the profile, complete it, and ask recent happy customers for reviews there. Engines repeatedly cite these pages "
               "for 'best X in city' questions.",
        "references": [GBP_RANKING],
    },
    "directory_presence": {
        "title": "Get listed on the directories engines cite",
        "how": "Claim or create your listing with consistent name, address and phone. For curated lists (e.g. 'best of' rankings), "
               "check their submission or review process.",
        "references": [],
    },
    "editorial_outreach": {
        "title": "Get included in the articles engines cite",
        "how": "Contact the author or publication with a short, specific pitch: what you do, proof (reviews, notable jobs), and why readers "
               "would benefit. Local press, 'best of' roundups and industry blogs all count.",
        "references": [GEO_PAPER],
    },
    "forum_presence": {
        "title": "Be part of the community threads engines cite",
        "how": "Engines cite Reddit and similar threads for recommendations. Don't spam: ask satisfied customers to share experiences, "
               "and answer questions helpfully under a clearly disclosed business account where the community allows it.",
        "references": [],
    },
    "social_presence": {
        "title": "Keep your social profiles complete and active",
        "how": "Use the same business name, description and links everywhere so engines connect the profiles to you.",
        "references": [],
    },
    "query_content": {
        "title": "Publish content for the questions where you never appear",
        "how": "For each question, create or improve a page that directly answers it, names your city and service, and shows proof.",
        "references": [GEO_PAPER],
    },
}

SOURCE_TYPE_TECHNIQUE = {
    "reviews": "review_site_presence",
    "marketplace": "directory_presence",
    "maps": "maps_listings",
    "forum": "forum_presence",
    "social": "social_presence",
    "reference": "editorial_outreach",
    "editorial": "editorial_outreach",
}
