from openai import OpenAI

from config import API_KEY, BASE_URL, MODEL, TEMPERATURE


def create_client():
    return OpenAI(
        base_url=BASE_URL,
        api_key=API_KEY,
    )


def get_ai_response(client, messages):
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
    )

    return response.choices[0].message.content
