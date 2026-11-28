"""Protocol serialization only. Business validation and pinned HTTP are shared.

No adapter streams or retries. Reasoning models omit optional JSON/temperature
parameters; their structured result still passes the existing exchange gate.
"""
import re
from fastapi import HTTPException


def model_path(model):
    # Model IDs are opaque for other APIs, but Gemini embeds them in a path.
    value=model.removeprefix('models/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}',value):
        raise HTTPException(422,'Gemini Model ID 只能包含字母、数字、点、下划线和连字符')
    return value


def request(provider,system,user,images=()):
    if not getattr(provider,'text',True):raise HTTPException(422,'所选模型未启用文本生成能力')
    if images and not provider.vision:raise HTTPException(422,'所选模型未启用图片理解能力')
    if provider.kind=='openai':
        content=user if not images else [{'type':'text','text':user}]+[{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+image,'detail':'low'}} for image in images]
        payload={'model':provider.model,'messages':[{'role':getattr(provider,'system_role','system'),'content':system},{'role':'user','content':content}],'stream':False}
        token_parameter=getattr(provider,'token_parameter','auto')
        if token_parameter=='auto':token_parameter='max_completion_tokens' if getattr(provider,'reasoning',False) else 'max_tokens'
        if token_parameter!='omit':payload[token_parameter]=provider.max_output_tokens
        if getattr(provider,'json_mode',True) and not getattr(provider,'reasoning',False):payload['response_format']={'type':'json_object'}
        return '/chat/completions',payload
    if provider.kind=='ollama':
        message={'role':'user','content':user}
        if images:message['images']=list(images)
        payload={'model':provider.model,'messages':[{'role':'system','content':system},message],'options':{'num_predict':provider.max_output_tokens},'stream':False}
        if getattr(provider,'json_mode',True) and not getattr(provider,'reasoning',False):payload['format']='json'
        return '/api/chat',payload
    if provider.kind=='anthropic':
        content=[{'type':'text','text':user}]+[{'type':'image','source':{'type':'base64','media_type':'image/jpeg','data':image}} for image in images]
        return '/messages',{'model':provider.model,'system':system,'messages':[{'role':'user','content':content}],'max_tokens':provider.max_output_tokens,'stream':False}
    if provider.kind=='gemini':
        payload={'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':user}]+[{'inlineData':{'mimeType':'image/jpeg','data':image}} for image in images]}],'generationConfig':{'maxOutputTokens':provider.max_output_tokens}}
        if getattr(provider,'json_mode',True) and not getattr(provider,'reasoning',False):payload['generationConfig']['responseMimeType']='application/json'
        return '/models/'+model_path(provider.model)+':generateContent',payload
    raise HTTPException(422,'不支持的模型协议')


def response(provider,value):
    if not isinstance(value,dict):raise ValueError('模型响应不是对象')
    if provider.kind=='openai':
        content=value['choices'][0]['message']['content'];usage=value.get('usage') or {};counts=(usage.get('prompt_tokens'),usage.get('completion_tokens'))
    elif provider.kind=='ollama':
        content=value['message']['content'];counts=(value.get('prompt_eval_count'),value.get('eval_count'))
    elif provider.kind=='anthropic':
        content=''.join(part['text'] for part in value['content'] if part.get('type')=='text')
        usage=value.get('usage') or {};counts=(usage.get('input_tokens'),usage.get('output_tokens'))
    else:
        content=''.join(part['text'] for part in value['candidates'][0]['content']['parts'] if 'text' in part and not part.get('thought'))
        usage=value.get('usageMetadata') or {}
        output=usage.get('candidatesTokenCount');thoughts=usage.get('thoughtsTokenCount',0)
        if type(output) is int and type(thoughts) is int and thoughts>=0:output+=thoughts
        else:output=None
        counts=(usage.get('promptTokenCount'),output)
    if not isinstance(content,str) or not content:raise ValueError('模型正文不是文本')
    known=all(type(v) is int and 0<=v<=10000000 for v in counts)
    return content,counts if known else (0,0),known


def models_path(provider):
    return '/api/tags' if provider.kind=='ollama' else '/models'


def models(provider,value):
    if not isinstance(value,dict):raise ValueError('模型列表不是对象')
    rows=value.get('models') if provider.kind in {'gemini','ollama'} else value.get('data')
    if not isinstance(rows,list) or len(rows)>5000:raise ValueError('模型列表无效或过大')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise ValueError('模型列表条目无效')
        if provider.kind=='gemini' and 'generateContent' not in row.get('supportedGenerationMethods',[]):continue
        identity=row.get('name') if provider.kind in {'gemini','ollama'} else row.get('id')
        if provider.kind=='gemini' and isinstance(identity,str):identity=identity.removeprefix('models/')
        if not isinstance(identity,str) or not 1<=len(identity)<=200 or any(ord(c)<32 for c in identity):raise ValueError('模型标识无效')
        if identity in seen:continue
        seen.add(identity);result.append({'id':identity,'name':str(row.get('displayName') or row.get('display_name') or identity)[:200]})
    # No capability inference from names or a remote marketing description.
    return result
