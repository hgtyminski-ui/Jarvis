from openai import OpenAI


def create_client(config):
    return OpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
    )


def get_ai_response(client, messages, config):
    response = client.chat.completions.create(
        model=config["model"],
        messages=messages,
        temperature=config["temperature"],
    )

    return response.choices[0].message.content
