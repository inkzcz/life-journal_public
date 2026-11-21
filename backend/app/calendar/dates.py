"""Explicit solar/lunar recurrence policies, never fixed-day lunar approximations."""
from datetime import date,timedelta
from typing import Literal
from pydantic import Field,model_validator
from lunardate import LunarDate
from ..content_schemas import StrictModel

class DateRule(StrictModel):
    calendar:Literal['solar','lunar']='solar'
    year:int=Field(ge=1,le=9998)
    month:int=Field(ge=1,le=12)
    day:int=Field(ge=1,le=31)
    leap_month:bool=False
    repeat:Literal['once','yearly','monthly','weekly','interval']='yearly'
    interval:int=Field(1,ge=1,le=366)
    missing:Literal['skip','last_day','march_1']='skip'
    lunar_leap:Literal['skip','regular']='skip'
    @model_validator(mode='after')
    def check(self):
        if self.calendar=='lunar':
            if not 1900<=self.year<=2099:raise ValueError('农历支持1900–2099年')
            if self.missing=='march_1':raise ValueError('农历不存在日期只支持跳过或月末')
            if self.repeat not in ('once','yearly'):raise ValueError('农历支持单次和每年重复')
            LunarDate(self.year,self.month,self.day,self.leap_month).toSolarDate()
        else:
            date(self.year,self.month,self.day)
            if self.leap_month:raise ValueError('公历没有农历闰月')
        return self

def occurrence(rule:DateRule,year:int,month:int|None=None):
    try:
        if rule.calendar=='lunar':
            if not 1900<=year<=2099:return None
            leap=rule.leap_month
            if leap and LunarDate.leapMonthForYear(year)!=rule.month:
                if rule.lunar_leap=='skip':return None
                leap=False
            return LunarDate(year,rule.month,rule.day,leap).toSolarDate()
        return date(year,month or rule.month,rule.day)
    except ValueError:
        if rule.calendar=='lunar':
            if rule.missing=='last_day' and 1900<=year<=2099:
                try:return LunarDate(year,rule.month,29,rule.leap_month and LunarDate.leapMonthForYear(year)==rule.month).toSolarDate()
                except ValueError:return None
            return None
        if rule.missing=='skip':return None
        import calendar
        m=month or rule.month
        if rule.missing=='march_1' and m==2 and rule.day==29:return date(year,3,1)
        return date(year,m,calendar.monthrange(year,m)[1])

def occurrences(rule:DateRule,start:date,end:date):
    if start>end:return []
    if (end-start).days>366*201:raise ValueError('查询范围不能超过201年')
    if rule.repeat=='once':
        d=occurrence(rule,rule.year)
        return [d] if d and start<=d<=end else []
    if rule.repeat in ('weekly','interval'):
        origin=date(rule.year,rule.month,rule.day);step=7*rule.interval if rule.repeat=='weekly' else rule.interval
        first=origin+timedelta(days=max(0,((start-origin).days+step-1)//step)*step)
        return [first+timedelta(days=n*step) for n in range(max(0,(end-first).days//step+1))]
    out=[]
    # Lunar year may map into January/February of the next Gregorian year.
    for year in range(max(rule.year,start.year-1),min(9998,end.year)+1):
        for month in (range(1,13) if rule.repeat=='monthly' else [None]):
            if rule.repeat=='yearly' and (year-rule.year)%rule.interval:continue
            if rule.repeat=='monthly' and ((year-rule.year)*12+(month-rule.month))%rule.interval:continue
            d=occurrence(rule,year,month)
            if d and occurrence(rule,rule.year)<=d and start<=d<=end:out.append(d)
    return sorted(set(out))

def years_at(rule:DateRule,d:date):
    if rule.calendar=='lunar':return LunarDate.fromSolarDate(d.year,d.month,d.day).year-rule.year
    return d.year-rule.year
