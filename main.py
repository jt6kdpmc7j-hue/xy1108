import os
import asyncio
from telebot.async_telebot import AsyncTeleBot
from fastapi import FastAPI

# ================== 🛠️ 基础配置区 ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8731091260:AAH8CPNrPpJkjVGrdpHtzNM9tRKiyREqI04")
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1003836886260")) # 👈 记得带负号
# ==================================================

bot = AsyncTeleBot(BOT_TOKEN)
app = FastAPI()

# 💡 核心数据库（生产环境建议换成 SQLite/MySQL，此处用内存字典演示）
# 1. 记录哪个用户对应群里的哪个话题 -> { user_id : topic_id }
user_to_topic = {}
# 2. 记录群里的某条转发消息对应哪位原始用户 -> { group_msg_id : user_id }
msg_to_user = {}

# ======= 核心逻辑：自动创建话题与双向分流 =======

@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'voice', 'video', 'document'])
async def handle_all_messages(message):
    chat_id = message.chat.id
    
    # ----------------------------------------------------
    # 场景 A：当【普通用户 A/B/C】给机器人发私聊消息时
    # ----------------------------------------------------
    if message.chat.type == "private":
        user_id = message.chat.id
        user_name = message.from_user.full_name or f"用户_{user_id}"
        
        # 💡 【核心逻辑】如果该用户是第一次来，自动在群里为他开辟一个“独立话题”
        if user_id not in user_to_topic:
            try:
                # 调用 TG 官方接口自动建群话题
                new_topic = await bot.create_forum_topic(
                    chat_id=ADMIN_GROUP_ID,
                    name=f"👤 {user_name} ({user_id})"  # 话题名：👤 张三 (123456)
                )
                user_to_topic[user_id] = new_topic.message_thread_id
                
                # 在这个新话题里发送一条握手通知
                await bot.send_message(
                    ADMIN_GROUP_ID,
                    f"🆕 **新客户接入**\n用户姓名: {user_name}\n用户ID: `{user_id}`\n可以在本话题下直接回复对方！",
                    message_thread_id=user_to_topic[user_id],
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"❌ 自动创建话题失败，请检查机器人群管理员权限！错误: {e}")
                return

        # 找到该用户的专属话题 ID
        target_topic_id = user_to_topic[user_id]
        
        # 将用户发的消息，“隔开”投递到他的专属话题里
        # 这里以文本消息为例，如需转发媒体可以扩展
        if message.text:
            forwarded = await bot.send_message(
                ADMIN_GROUP_ID,
                f"💬 **{user_name}**:\n{message.text}",
                message_thread_id=target_topic_id
            )
            # 记录消息 ID 映射，方便你在群里回复
            msg_to_user[forwarded.message_id] = user_id
        else:
            # 如果是图片/语音等，直接转发过去
            forwarded = await bot.forward_message(
                chat_id=ADMIN_GROUP_ID,
                from_chat_id=user_id,
                message_id=message.message_id,
                message_thread_id=target_topic_id
            )
            msg_to_user[forwarded.message_id] = user_id


    # ----------------------------------------------------
    # 场景 B：当你在【管理群】的某个话题格子里回复消息时
    # ----------------------------------------------------
    elif chat_id == ADMIN_GROUP_ID:
        # 必须是右键/长按某条消息选择“回复(Reply)”
        if message.reply_to_message and message.reply_to_message.message_id in msg_to_user:
            original_user_id = msg_to_user[message.reply_to_message.message_id]
            try:
                # 机器人把你在话题里输入的话，私聊传回给那个特定用户
                if message.text:
                    await bot.send_message(original_user_id, message.text)
                # 如果你在群里回复的是图片/文件，同样传回给用户
                else:
                    await bot.copy_message(chat_id=original_user_id, from_chat_id=ADMIN_GROUP_ID, message_id=message.message_id)
            except Exception as e:
                await bot.send_message(
                    ADMIN_GROUP_ID, 
                    f"❌ 回复失败，用户可能停用了机器人。错误: {e}", 
                    message_thread_id=message.message_thread_id
                )

# ======= 异步启动配置 =======
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(bot.polling(non_stop=True))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
