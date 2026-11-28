"""Editable starting addresses, not a model catalogue or compatibility guarantee.

Official documentation sources are shipped with every preset for inspection.
"""
PRESETS=[
    {'id':'openai','name':'OpenAI','kind':'openai','base_url':'https://api.openai.com/v1','docs':'https://platform.openai.com/docs/api-reference/chat'},
    {'id':'deepseek','name':'DeepSeek','kind':'openai','base_url':'https://api.deepseek.com','docs':'https://api-docs.deepseek.com/'},
    {'id':'bailian','name':'阿里云百炼','kind':'openai','base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','docs':'https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope'},
    {'id':'volcengine','name':'火山引擎','kind':'openai','base_url':'https://ark.cn-beijing.volces.com/api/v3','docs':'https://www.volcengine.com/docs/82379/1330310'},
    {'id':'siliconflow','name':'硅基流动','kind':'openai','base_url':'https://api.siliconflow.cn/v1','docs':'https://docs.siliconflow.cn/cn/api-reference/chat-completions/chat-completions'},
    {'id':'zhipu','name':'智谱 AI','kind':'openai','base_url':'https://open.bigmodel.cn/api/paas/v4','docs':'https://docs.bigmodel.cn/cn/api/introduction'},
    {'id':'gemini','name':'Google Gemini','kind':'gemini','base_url':'https://generativelanguage.googleapis.com/v1beta','docs':'https://ai.google.dev/api/generate-content'},
    {'id':'anthropic','name':'Anthropic Claude','kind':'anthropic','base_url':'https://api.anthropic.com/v1','docs':'https://docs.anthropic.com/en/api/messages'},
    {'id':'openrouter','name':'OpenRouter','kind':'openai','base_url':'https://openrouter.ai/api/v1','docs':'https://openrouter.ai/docs/api-reference/overview'},
    {'id':'ollama','name':'Ollama','kind':'ollama','base_url':'http://127.0.0.1:11434','docs':'https://docs.ollama.com/api/chat'},
    {'id':'lmstudio','name':'LM Studio','kind':'openai','base_url':'http://localhost:1234/v1','docs':'https://lmstudio.ai/docs/developer/openai-compat'},
    {'id':'custom','name':'自定义兼容接口','kind':'openai','base_url':'https://example.com/v1','docs':'https://platform.openai.com/docs/api-reference/chat'},
]
