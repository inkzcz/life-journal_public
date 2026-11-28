import {expect,it} from 'vitest'
import {formatRecoveryTime} from './dates'
it('formats stored UTC with explicit configured zone without mutating input',()=>{
 const value='2026-11-01T05:30:00Z'
 expect(formatRecoveryTime(value,'Asia/Shanghai')).toContain('13:30:00')
 expect(formatRecoveryTime(value,'America/New_York')).toContain('01:30:00')
 expect(formatRecoveryTime('2026-11-01T06:30:00Z','America/New_York')).toContain('01:30:00')
 expect(value).toBe('2026-11-01T05:30:00Z')
})
it('handles invalid time and zone without exposing raw arbitrary input',()=>{
 expect(formatRecoveryTime('invalid','UTC')).toBe('时间未知')
 expect(formatRecoveryTime('2026-01-01T00:00:00Z','invalid')).toContain('UTC')
})
