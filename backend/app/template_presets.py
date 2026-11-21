"""Editable starting points only. Runtime rendering never branches on these keys."""
import uuid

PRESETS={
 'travel':('旅行记录',[('目的地','short_text','行程概览'),('出发日期','date','行程概览'),('返回日期','date','行程概览'),('同行人','short_text','旅途细节'),('住宿','long_text','旅途细节')],['header','summary','body','gallery','timeline','related']),
 'gift':('礼物记录',[('礼物名称','short_text','礼物信息'),('赠送对象','short_text','礼物信息'),('赠送日期','date','礼物信息'),('场合','short_text','礼物信息'),('描述','long_text','礼物故事')],['header','fields','gallery','body','related']),
 'album':('生活相册',[('相册名称','short_text','相册信息'),('日期','date','相册信息'),('地点','short_text','相册信息'),('描述','long_text','相册信息')],['header','summary','gallery','body','related']),
 'anniversary':('纪念日记录',[('纪念日名称','short_text','纪念信息'),('日期','date','纪念信息'),('相关人物','short_text','纪念信息')],['header','fields','body','gallery','related']),
}

def presets():
    result=[]
    for key,(name,specs,kinds) in PRESETS.items():
        fields=[{'key':str(uuid.uuid4()),'group':group,'field':{'kind':kind,'name':label,'position':i,'description':'','active':True,'required':False,'has_default':False,'default_value':None,'rules':{}}} for i,(label,kind,group) in enumerate(specs)]
        modules=[{'id':str(uuid.uuid4()),'kind':kind,'title':{'summary':'记录摘要','fields':'值得珍藏的信息','gallery':'影像片刻','timeline':'时间线','related':'沿着故事继续走'}.get(kind,''),'enabled':True,'layout':'date' if key=='anniversary' and kind=='fields' else 'masonry' if key=='album' and kind=='gallery' else 'card' if kind=='fields' else 'grid','field_ids':[f['key'] for f in fields if kind!='timeline' or f['field']['kind']=='date'] if kind in {'summary','fields','timeline'} else []} for kind in kinds]
        if key=='travel':
            next(m for m in modules if m['kind']=='gallery')['group_by']='date'
            modules.extend({'id':str(uuid.uuid4()),'kind':k,'title':title,'enabled':True,'layout':'grid','field_ids':[]} for k,title in [('itinerary','旅途日程'),('map','故事里的地点')])
        if key=='album':
            next(m for m in modules if m['kind']=='gallery')['group_by']='manual'
        result.append({'key':key,'slug':key+'-'+uuid.uuid4().hex[:8],'name':name,'description':'可自由修改的初始模板；正文、封面与照片复用现有记录和媒体能力。','active':True,'fields':fields,'modules':modules})
    return result
