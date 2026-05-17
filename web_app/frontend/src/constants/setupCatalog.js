// web_app/frontend/src/constants/setupCatalog.js
// Static catalog for the first-run setup wizard — Epic #91 (M2).
// No I/O. No deps. Public company names only.

export const CANONICAL_ROLES = [
  'Software Engineer',
  'Senior Software Engineer',
  'Staff Software Engineer',
  'Principal Software Engineer',
  'Engineering Manager',
  'Data Engineer',
  'Senior Data Engineer',
  'Staff Data Engineer',
  'Analytics Engineer',
  'ML Engineer',
  'ML Platform Engineer',
  'Data Scientist',
  'Senior Data Scientist',
  'Product Manager',
  'Senior Product Manager',
  'Engineering Lead',
  'Solutions Architect',
  'Site Reliability Engineer',
  'Platform Engineer',
  'Full Stack Engineer',
]

export const CANONICAL_COMPANIES = [
  // Big tech
  'Apple', 'Google', 'Microsoft', 'Amazon', 'Meta', 'Netflix', 'Nvidia',
  // AI labs
  'Anthropic', 'OpenAI', 'Cohere', 'Mistral AI', 'Hugging Face', 'Perplexity',
  // Fintech
  'Stripe', 'Plaid', 'Block', 'Adyen', 'Brex', 'Ramp', 'Affirm', 'Robinhood',
  'Coinbase', 'Wise', 'Mercury', 'Chime', 'Klarna',
  // Data / DevTools
  'Snowflake', 'Databricks', 'Confluent', 'MongoDB', 'Elastic', 'HashiCorp',
  'GitHub', 'GitLab', 'Datadog', 'New Relic', 'Splunk', 'PagerDuty',
  'Fivetran', 'dbt Labs', 'Airbyte', 'Prefect', 'Astronomer',
  // SaaS / Productivity
  'Atlassian', 'Notion', 'Linear', 'Figma', 'Canva', 'Asana', 'Monday.com',
  'Zoom', 'Slack', 'Dropbox', 'Box', 'DocuSign', 'Twilio', 'Zendesk',
  // E-commerce / Marketplaces
  'Shopify', 'Etsy', 'eBay', 'Airbnb', 'Booking.com', 'Expedia',
  'Uber', 'Lyft', 'DoorDash', 'Instacart', 'Wayfair',
  // Streaming / Media
  'Spotify', 'Disney', 'Roku', 'Hulu', 'Pinterest', 'Reddit', 'Snap',
  'TikTok', 'Discord',
  // Enterprise / Cloud
  'Salesforce', 'Oracle', 'SAP', 'ServiceNow', 'Workday', 'VMware', 'IBM',
  'Cisco', 'Cloudflare', 'Akamai', 'Fastly',
  // Hardware / Auto
  'Tesla', 'Rivian', 'SpaceX', 'AMD', 'Intel', 'Qualcomm',
  // Consulting / Finance
  'McKinsey', 'BCG', 'Bain', 'Deloitte', 'Accenture',
  'Goldman Sachs', 'Morgan Stanley', 'JPMorgan Chase', 'BlackRock', 'Citadel',
  'Two Sigma', 'Jane Street', 'Hudson River Trading',
  // Logistics / Industry
  'FedEx', 'UPS', 'Walmart', 'Target', 'Costco',
  // Bio / Health tech
  'Moderna', 'Pfizer', 'Genentech', 'Illumina', '23andMe', 'Tempus',
  // Misc unicorns
  'Palantir', 'CrowdStrike', 'Okta', 'Snowflake', 'ZScaler', 'Wiz',
  'Anduril', 'Scale AI', 'Replit', 'Vercel', 'Netlify', 'Supabase',
  'Clerk', 'PostHog', 'Sentry', 'Retool', 'Airtable',
]

// Convenience bundles — each item must also exist in CANONICAL_COMPANIES above.
export const COMPANY_BUNDLES = {
  FAANG: ['Meta', 'Apple', 'Amazon', 'Netflix', 'Google'],
  'Top fintech': ['Stripe', 'Plaid', 'Block', 'Brex', 'Ramp', 'Coinbase', 'Mercury'],
  'AI labs': ['Anthropic', 'OpenAI', 'Cohere', 'Mistral AI', 'Hugging Face', 'Perplexity'],
}
