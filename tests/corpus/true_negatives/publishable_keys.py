"""Keys that are published deliberately. Committing one is not a compromise.

Measured as Critical false positives in browser-use (PostHog project key) and langgraph
(Supabase anon key). These must still be reported - the publishable and secret halves are
easy to confuse - but at Low, not Critical.
"""

POSTHOG_PROJECT_API_KEY = "phc_F8JMNjW1i2KbGUTaW1unnDdLSPCoyc52SGRU0Jeca"
STRIPE_PUBLISHABLE_KEY = "pk_live_51H8xKqLmQp4RtVzYwB7NcJdH"
