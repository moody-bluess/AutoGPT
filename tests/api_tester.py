import json

import requests

url = "http://llm.api.corp.qunar.com/algo/llm/api"
headers = {
    "Content-Type": "application/json"
}

msg = '你是一名专业的小红书旅游文案运营专家，现在需要你写一篇小红书风格的《越南芽庄》的旅游指南- 请注意，你的文案应当使用有趣、引人入胜的标题，激发读者的好奇心，例如使用短小精悍的词语或者问句形式。例如："迷失在花海中的绝美芽庄之旅"；' \
      '带有独特的体验和亮点：分享旅行中的独特体验和亮点，这可以是不寻常的景点、特色文化活动、当地美食或其他令人印象深刻的事物。使用生动的语言描述，让读者感受到你的热情和情感；' \
      '实用的建议和小贴士：提供实用的旅行建议和小贴士，例如如何规划行程、最佳的交通方式、推荐的餐厅或住宿等。这些建议可以帮助读者更好地计划自己的旅行；' \
      '真实的故事和感受：分享自己的旅行故事和感受，让读者更加亲近你的旅行经历。使用生动的描写和个人感受，让读者感受到你的情感和体验。文案排版和格式：' \
      '使用清晰简洁的段落和标题，使得笔记易于阅读和理解。使用适当的字体、字号和行距，让文字排版整齐美观。使用分段和标点符号，帮助读者更好地理解和流畅阅读。' \
      '适度使用表情符号来增添笔记的趣味性和情感表达，但不要过度使用。选择与内容和情绪相符的表情符号，能够更好地传达你的情感和态度。' \
      '推荐适最佳的旅游时间、交通工具、景点、吃喝玩乐等项目。'
prompt = {
    "messages": [{"role": "user", "content": msg}],
    "temperature": 0.7
}
data = {
    "key": "qunar_hackathon_41",
    "password": "1MVb45",
    "prompt": prompt,
    "apiType": "gpt-35-turbo-16k",
    "apiVersion": "2023-05-15",
    "appCode": "-----",
    "traceId": "123",
    "userIdentityInfo": "lianchen.zhang",
    "version": "hard",
    "project": "售后客服对话总结"
}
data = json.dumps(data).encode()
# response = requests.post(url, headers=headers, data=)
s = requests.Session()

response = s.request(url=url, method='post', headers=headers, data=data)
formatted_response = json.loads(response.text)

reply = formatted_response["data"]["reply"]
print('\n\n')
print(reply)
