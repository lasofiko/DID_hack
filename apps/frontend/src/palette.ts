// Shared canvas palette; matching CSS variables are declared in style.css.
export const palette = {
 background:'#111119', map:'#151620', grid:'#252838', free:[36,39,53], wall:[126,136,162], unknown:[21,22,32],
 accent:'#b3a0ff', trajectory:'#83d5ff', robot:'#ffd080', robotInk:'#342715', base:'#c8d0e7',
 prior:'#9ca8bf', ink:'#111119', text:'#eef0f9', muted:'#adb5ca',
 energyLow:[95,132,224], energyMid:[177,143,232], energyHigh:[244,177,99],
} as const;
export const FIXED_ENERGY_MAX=12;
