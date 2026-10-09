import {translator} from '../src/i18n/core.ts';
const t=translator('ru-RU');
t('mission.start');
t('mission.accepted',{command:'Пауза'});
t('agent.complete',{delivered:2,total:3});
// @ts-expect-error: missing key must fail compilation
t('mission.notAKey');
// @ts-expect-error: missing parameter must fail compilation
t('mission.accepted');
// @ts-expect-error: a translated message cannot accept the wrong parameter
t('mission.accepted',{cmd:'Пауза'});
// @ts-expect-error: unused parameters are not accepted
t('mission.start',{unused:1});
// @ts-expect-error: unsupported locale is not accepted
translator('en-US');
