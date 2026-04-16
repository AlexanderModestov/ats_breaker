import type { MetadataRoute } from 'next'

const SITE_URL = 'https://hrbreaker.co'

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date()

  return [
    {
      url: `${SITE_URL}/`,
      lastModified: now,
      changeFrequency: 'weekly',
      priority: 1,
    },
    {
      url: `${SITE_URL}/pricing`,
      lastModified: now,
      changeFrequency: 'monthly',
      priority: 0.9,
    },
    // Add these once the pages ship:
    // { url: `${SITE_URL}/about`,   lastModified: now, changeFrequency: 'monthly', priority: 0.7 },
    // { url: `${SITE_URL}/privacy`, lastModified: now, changeFrequency: 'yearly',  priority: 0.3 },
    // { url: `${SITE_URL}/terms`,   lastModified: now, changeFrequency: 'yearly',  priority: 0.3 },
    // { url: `${SITE_URL}/blog`,    lastModified: now, changeFrequency: 'weekly',  priority: 0.8 },
  ]
}
