import {ru} from './ru.ts';
import {tt} from './tt.ts';
export type Locale = 'ru-RU'|'tt-RU';
export type Key = keyof typeof ru;
type Params<S extends string> = S extends `${string}{${infer P}}${infer Rest}` ? P|Params<Rest> : never;
export type Translator = <K extends Key>(key: K, ...args: [Params<typeof ru[K]>] extends [never] ? [] : [Record<Params<typeof ru[K]>, string|number>]) => string;
export const dictionaries = {'ru-RU': ru, 'tt-RU': tt};
export const STORAGE_KEY = 'did-lab.locale';
export function validLocale(value: unknown): Locale {return value === 'tt-RU' ? 'tt-RU' : 'ru-RU'}
export function translator(locale: Locale): Translator {
 return ((key: Key, params?: Record<string,string|number>) => dictionaries[locale][key].replace(/\{(\w+)\}/g, (_, name: string) => String(params?.[name] ?? `{${name}}`))) as Translator;
}
export function number(locale: Locale, value: number, digits = 1) {
 return new Intl.NumberFormat(locale, {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(value);
}
