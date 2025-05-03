from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI(
    api_key="sk-WkYTI6iPaFDAqQdMFd612bD34eAc4e918cC8F5Bf5cC86d8e",
    base_url="https://aihubmix.com/v1"
)
async def main():
    response = await client.responses.create(
        model="gemini-2.5-pro-exp-03-25",
        input=[
            {
                "role": "user",
                "content": [
                    { "type": "input_text", "text": "what is in this image?" },
                    {
                        "type": "input_image",
                        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
                    }
                ]
            }
        ]
    )

    print(response)

asyncio.run(main())