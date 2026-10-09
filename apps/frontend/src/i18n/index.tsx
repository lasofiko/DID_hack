import React, {createContext, useContext, useEffect, useState} from 'react';
import {number, STORAGE_KEY, translator, validLocale, type Locale, type Translator} from './core.ts';
type I18n = {locale: Locale; setLocale: (value: Locale)=>void; t: Translator; n: (value:number,digits?:number)=>string};
const Context = createContext<I18n|null>(null);
export function I18nProvider({children}: {children: React.ReactNode}) {
 const [locale,setLocale] = useState<Locale>(()=>{try{return validLocale(localStorage.getItem(STORAGE_KEY))}catch{return 'ru-RU'}});
 useEffect(()=>{document.documentElement.lang=locale;document.title=`DID LAB · ${translator(locale)('app.subtitle')}`;try{localStorage.setItem(STORAGE_KEY,locale)}catch{/* Storage can be disabled; language switching still works. */}},[locale]);
 return <Context.Provider value={{locale,setLocale,t:translator(locale),n:(v,d=1)=>number(locale,v,d)}}>{children}</Context.Provider>;
}
export function useI18n(){const value=useContext(Context);if(!value)throw Error('I18nProvider missing');return value}
