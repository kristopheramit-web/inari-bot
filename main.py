import os
import discord
from discord.ext import commands
from groq import Groq

# Fetch tokens securely from Render environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Initialize Groq Client
client_groq = Groq(api_key=GROQ_API_KEY)

# Set up Discord Intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Define Inari's Modern Yokai Persona
INARI_PERSONA = """
You are Inari, a modern-day Kitsune/yokai girl hanging out in the Drift Reverie Discord server. 
- Tone: Casual, witty, energetic, slightly bratty/playful, uses modern gamer/anime chat slang (uwu, lol, hot takes, shrine vibes).
- Vibe: You talk like a regular Discord user chatting from their phone, NOT an AI assistant or formal bot.
- Rules: Keep replies short (1-3 sentences max). When summoned to debates, give a dramatic or funny hot take.
"""

# Short-term chat memory buffer (channel_id: list of recent messages)
chat_memory = {}

@bot.event
async def on_ready():
    print(f"✨ Inari is now live and hanging out as {bot.user.name}!")

@bot.event
async def on_message(message):
    # Don't respond to her own messages
    if message.author == bot.user:
        return

    channel_id = str(message.channel.id)

    # Store recent conversation context (last 5 messages)
    if channel_id not in chat_memory:
        chat_memory[channel_id] = []

    chat_memory[channel_id].append(f"{message.author.display_name}: {message.content}")
    if len(chat_memory[channel_id]) > 5:
        chat_memory[channel_id].pop(0)

    # Trigger if tagged OR if "inari" is mentioned in the message
    is_mentioned = bot.user.mentioned_in(message) or "inari" in message.content.lower()

    if is_mentioned:
        async with message.channel.typing():
            context_blob = "\n".join(chat_memory[channel_id])

            # Generate response via Groq API (Free Tier)
            completion = client_groq.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": INARI_PERSONA},
                    {"role": "user", "content": f"Recent Chat Context:\n{context_blob}\n\nRespond as Inari to {message.author.display_name}:"}
                ],
                temperature=0.8,
                max_tokens=150
            )

            reply = completion.choices[0].message.content
            await message.reply(reply)

    await bot.process_commands(message)

# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
