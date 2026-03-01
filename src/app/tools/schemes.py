import boto3

from app.config import settings


def check_scheme_eligibility(farmer_profile: dict) -> dict:
    if not settings.amazon_q_app_id:
        return {"schemes": "Amazon Q Business not configured", "sources": []}

    query_parts = []
    if farmer_profile.get("land_holding"):
        query_parts.append(f"land holding {farmer_profile['land_holding']} acres")
    if farmer_profile.get("state"):
        query_parts.append(f"in {farmer_profile['state']}")
    if farmer_profile.get("crop"):
        query_parts.append(f"growing {farmer_profile['crop']}")
    if farmer_profile.get("category"):
        query_parts.append(f"category {farmer_profile['category']}")

    query = "What government schemes is a farmer eligible for with " + ", ".join(query_parts) + "?"

    try:
        client = boto3.client("qbusiness", region_name=settings.aws_default_region)
        response = client.chat_sync(
            applicationId=settings.amazon_q_app_id,
            userMessage=query,
        )
        return {
            "schemes": response.get("systemMessage", ""),
            "sources": [
                s.get("title", "") for s in response.get("sourceAttributions", [])
            ],
        }
    except Exception as e:
        return {"error": str(e)}
