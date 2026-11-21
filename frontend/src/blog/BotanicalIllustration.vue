<script setup lang="ts">
import {useId} from 'vue'
defineProps<{compact?:boolean}>()
// Per-instance paint servers: a sidebar and a reader ornament may coexist.
const id=useId().replace(/[^a-zA-Z0-9_-]/g,'')
const ref=(name:string)=>`url(#${id}-${name})`
const href=(name:string)=>`#${id}-${name}`
</script>
<template>
<svg class="botanical-illustration" :viewBox="compact?'0 0 180 74':'0 0 320 300'" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient :id="id+'-leaf'" x1="0" y1="1" x2="1" y2="0">
      <stop class="botanical-leaf-shadow" offset="0"/><stop class="botanical-leaf-mid" offset=".43"/><stop class="botanical-leaf-light" offset="1"/>
    </linearGradient>
    <linearGradient :id="id+'-petal'" x1=".15" y1="1" x2=".85" y2="0">
      <stop class="botanical-petal-shadow" offset="0"/><stop class="botanical-petal-mid" offset=".45"/><stop class="botanical-petal-light" offset="1"/>
    </linearGradient>
    <linearGradient :id="id+'-bell'" x1="0" y1="0" x2="1" y2="1">
      <stop class="botanical-bell-light" offset="0"/><stop class="botanical-bell-mid" offset=".55"/><stop class="botanical-bell-shadow" offset="1"/>
    </linearGradient>
    <linearGradient :id="id+'-wash'" x1="0" y1="0" x2="1" y2="1"><stop class="botanical-wash" offset="0"/><stop class="botanical-clear" offset="1"/></linearGradient>
    <!-- Hand-shaped lanceolate leaf: unequal lobes, curled tip, midrib and six fine veins. -->
    <g :id="id+'-leaf-shape'">
      <path :fill="ref('leaf')" class="botanical-leaf-edge" d="M0 0C8-17 25-29 51-29 45-23 42-12 30-6 18 1 9-3 0 0Z"/>
      <path class="botanical-leaf-fold" d="M1-1C19-10 35-20 50-28 38-14 24-4 1-1Z"/>
      <path class="botanical-vein" d="M0 0C17-10 33-19 49-28M12-7l1-10m10 4 1-10m10 3 1-7M12-7l13 1m-2-7 13-1m-3-6 10-1"/>
    </g>
    <!-- A second, broader contour prevents the sprig becoming a repeated icon. -->
    <g :id="id+'-round-leaf'">
      <path :fill="ref('leaf')" class="botanical-leaf-edge" d="M0 0C2-16 15-33 39-38 40-26 39-16 31-9 19 2 10-2 0 0Z"/>
      <path class="botanical-leaf-fold" d="M1-1C13-15 26-26 38-37 29-19 18-6 1-1Z"/>
      <path class="botanical-vein" d="M0 0C11-12 24-25 38-37M10-11 9-21m10 0 1-10M10-11l13-1m-4-9 13-2"/>
    </g>
    <!-- Pendant blossom, irregular flared rim, inner folds and small sepals. -->
    <g :id="id+'-bell-shape'">
      <path class="botanical-calyx" d="M-3 0 0-5 3 0 2 3-2 3Z"/>
      <path :fill="ref('bell')" class="botanical-bell-edge" d="M-2 1C-9 3-9 12-8 17-8 21-12 22-11 24-9 27-6 24-4 23-2 29 1 28 3 24 6 27 10 25 10 23 5 20 7 14 6 9 5 4 3 2 2 1Z"/>
      <path class="botanical-bell-fold" d="M-3 5C-6 11-3 20-4 23M2 5C5 11 1 18 3 24M-10 24c3-4 4-2 6-1m1 1q3-5 5 0"/>
      <path class="botanical-pollen" d="M-1 24v4m4-5 1 4"/>
    </g>
    <!-- Five individually drawn petals, with variable rotations in the flowering branch. -->
    <g :id="id+'-flower'">
      <g :fill="ref('petal')" class="botanical-petal-edge">
        <path d="M0 1C-6-3-9-11-5-16-1-21 4-17 5-13 6-7 2-3 0 1Z"/>
        <path d="M0 0C2-8 8-14 13-11 20-8 15-1 10 2 6 4 3 1 0 0Z"/>
        <path d="M0 1C8 0 16 3 14 9 12 16 5 13 2 9 0 6 1 4 0 1Z"/>
        <path d="M0 1C3 8 1 17-5 17-13 16-10 8-6 5-4 2-2 2 0 1Z"/>
        <path d="M0 1C-6 6-15 5-16-1-16-9-8-8-4-4-1-2-1 0 0 1Z"/>
      </g>
      <path class="botanical-petal-vein" d="M0 1-3-12M0 1l11-8M0 1l11 8M0 1l-6 12M0 1l-12-3"/>
      <path class="botanical-flower-heart" d="M-2-2 1-3 3 0 1 3-2 2-3 0Z"/>
      <path class="botanical-pollen" d="m-2-1-2-3m5 3 3-2M0 2v4"/>
    </g>
    <g :id="id+'-bud'">
      <path :fill="ref('petal')" class="botanical-petal-edge" d="M0 2C-7-3-7-13-1-18 5-16 7-7 0 2Z"/>
      <path class="botanical-petal-vein" d="M0 1-1-14"/><path class="botanical-calyx" d="M-3-1 0 5 3-2 0 0Z"/>
    </g>
  </defs>
  <!-- A separately composed header sprig; no cropped sidebar artwork. -->
  <template v-if="compact">
    <g class="botanical-celadon">
      <path class="botanical-stem" d="M12 63C43 47 68 29 101 24s47 4 67 13M58 39q-2-10 0-18M90 25q15 7 18 19M130 27q13 7 14 20"/>
      <use :href="href('leaf-shape')" transform="translate(31 53) rotate(-40) scale(.62)"/>
      <use :href="href('leaf-shape')" transform="translate(51 42) rotate(28) scale(.67)"/>
      <use :href="href('round-leaf')" transform="translate(76 31) rotate(-8) scale(.65)"/>
      <use :href="href('leaf-shape')" transform="translate(116 26) rotate(35) scale(.6)"/>
      <path class="botanical-stem" d="M101 34q-1 8 1 11m28-13q4 7 3 13m24-10q4 8 3 14"/>
      <use :href="href('bell-shape')" transform="translate(102 45) scale(.67)"/>
      <use :href="href('bell-shape')" transform="translate(133 45) scale(.65)"/>
      <use :href="href('bell-shape')" transform="translate(160 49) scale(.6)"/>
    </g>
    <g class="botanical-lilac">
      <path class="botanical-stem" d="M13 65C52 46 78 33 111 26l51-12M54 44 57 22M94 31l6 22m30-31 5 20m-3-21 8-11"/>
      <use :href="href('round-leaf')" transform="translate(30 56) rotate(-50) scale(.56)"/>
      <use :href="href('leaf-shape')" transform="translate(55 43) rotate(48) scale(.58)"/>
      <use :href="href('leaf-shape')" transform="translate(100 31) rotate(-5) scale(.6)"/>
      <use :href="href('flower')" transform="translate(59 23) rotate(10) scale(.65)"/>
      <use :href="href('flower')" transform="translate(91 32) rotate(-24) scale(.73)"/>
      <use :href="href('flower')" transform="translate(100 53) rotate(30) scale(.55)"/>
      <use :href="href('flower')" transform="translate(134 41) rotate(-10) scale(.7)"/>
      <use :href="href('bud')" transform="translate(141 11) rotate(40) scale(.6)"/>
      <use :href="href('bud')" transform="translate(164 14) rotate(55) scale(.5)"/>
    </g>
  </template>
  <template v-else>
  <!-- Celadon: an arch rising from the lower left, with drooping ivory bells. -->
  <g class="botanical-celadon">
    <path :fill="ref('wash')" d="M0 164C48 156 57 216 106 231 157 246 197 252 252 300H0Z"/>
    <path class="botanical-mist" d="M0 246C73 208 113 256 186 266 233 272 269 291 305 300H0Z"/>
    <g opacity=".28" transform="translate(-15 82) rotate(14)"><path class="botanical-stem" d="M15 190C24 115 55 73 110 44"/><use :href="href('round-leaf')" transform="translate(33 136) rotate(-53) scale(.9)"/><use :href="href('leaf-shape')" transform="translate(51 98) rotate(23) scale(1.1)"/><use :href="href('leaf-shape')" transform="translate(76 70) rotate(-30) scale(.75)"/></g>
    <path class="botanical-stem botanical-trunk" d="M19 286C28 212 52 154 102 110 144 73 199 60 275 79"/>
    <path class="botanical-stem" d="M39 216C32 179 29 151 41 121M61 167C91 166 113 174 143 195M104 109C102 77 111 49 130 28M141 83C164 95 178 108 188 127M184 72C211 94 230 112 238 135M218 72C243 85 264 98 278 122M83 128C58 125 50 111 47 92"/>
    <use :href="href('round-leaf')" transform="translate(38 196) rotate(-63) scale(1.16)"/>
    <use :href="href('leaf-shape')" transform="translate(45 209) rotate(19) scale(1.2)"/>
    <use :href="href('leaf-shape')" transform="translate(63 166) rotate(64) scale(1.25)"/>
    <use :href="href('round-leaf')" transform="translate(83 129) rotate(-110) scale(.83)"/>
    <use :href="href('leaf-shape')" transform="translate(106 105) rotate(-44) scale(1.23)"/>
    <use :href="href('leaf-shape')" transform="translate(121 94) rotate(38) scale(1.34)"/>
    <use :href="href('round-leaf')" transform="translate(156 77) rotate(-4) scale(1.32)"/>
    <use :href="href('leaf-shape')" transform="translate(190 73) rotate(44) scale(1.08)"/>
    <use :href="href('leaf-shape')" transform="translate(226 76) rotate(39) scale(1.02)"/>
    <use :href="href('leaf-shape')" transform="translate(251 78) rotate(9) scale(.87)"/>
    <g class="botanical-stem"><path d="M163 101q-5 12-3 23M186 124q8 14 6 27M213 102q5 14 3 28M237 134q7 12 5 26M261 103q5 14 4 24M277 121q9 13 7 27"/></g>
    <use :href="href('bell-shape')" transform="translate(160 124) rotate(6) scale(1.1)"/>
    <use :href="href('bell-shape')" transform="translate(192 151) rotate(-8)"/>
    <use :href="href('bell-shape')" transform="translate(216 130) rotate(3) scale(1.06)"/>
    <use :href="href('bell-shape')" transform="translate(242 160) rotate(-12) scale(.91)"/>
    <use :href="href('bell-shape')" transform="translate(265 127) rotate(-8) scale(.78)"/>
    <use :href="href('bell-shape')" transform="translate(284 148) rotate(-14) scale(.95)"/>
    <use :href="href('leaf-shape')" transform="translate(225 213) rotate(49) scale(.5)" opacity=".6"/>
    <use :href="href('round-leaf')" transform="translate(270 246) rotate(108) scale(.35)" opacity=".4"/>
  </g>
  <!-- Lilac: a looser flowering bough, fine branching and a few drifting petals. -->
  <g class="botanical-lilac">
    <path :fill="ref('wash')" d="M0 166C36 173 54 228 109 241 163 254 230 266 277 300H0Z"/>
    <path class="botanical-mist" d="M0 253C55 230 96 247 152 273 199 289 264 281 310 300H0Z"/>
    <path class="botanical-stem botanical-trunk" d="M18 283C44 224 75 182 124 149 165 120 213 105 285 66"/>
    <path class="botanical-stem" d="M68 196C65 156 69 121 82 93M92 172C125 172 160 186 185 211M121 150C132 110 146 82 169 61M150 133C171 147 205 157 228 174M182 117C191 90 210 64 230 48M219 100C242 109 263 113 287 103M248 85C255 60 266 42 282 32"/>
    <use :href="href('round-leaf')" transform="translate(45 232) rotate(-54) scale(1.14)"/>
    <use :href="href('leaf-shape')" transform="translate(70 190) rotate(-100) scale(.85)"/>
    <use :href="href('leaf-shape')" transform="translate(111 173) rotate(58) scale(1.04)"/>
    <use :href="href('round-leaf')" transform="translate(124 145) rotate(-74) scale(.78)"/>
    <use :href="href('leaf-shape')" transform="translate(176 146) rotate(63) scale(.72)"/>
    <use :href="href('leaf-shape')" transform="translate(221 99) rotate(29) scale(.75)"/>
    <use :href="href('round-leaf')" transform="translate(253 82) rotate(-69) scale(.63)"/>
    <path class="botanical-stem" d="m79 119 14-8m30 38-12-21m31-26 15 5m-4-32-9-8m45 45 14 12m5-34 13 3m-1-29-9-10m32 44 9-16m24 3 13 1m-4-14 14-4"/>
    <use :href="href('flower')" transform="translate(92 109) rotate(-18) scale(.94)"/>
    <use :href="href('flower')" transform="translate(111 127) rotate(24) scale(1.03)"/>
    <use :href="href('flower')" transform="translate(156 107) rotate(-9) scale(1.15)"/>
    <use :href="href('flower')" transform="translate(145 66) rotate(31) scale(.86)"/>
    <use :href="href('flower')" transform="translate(194 125) rotate(13) scale(1.12)"/>
    <use :href="href('flower')" transform="translate(220 91) rotate(-25) scale(.92)"/>
    <use :href="href('flower')" transform="translate(212 53) rotate(12) scale(.72)"/>
    <use :href="href('flower')" transform="translate(250 76) rotate(31) scale(.81)"/>
    <use :href="href('flower')" transform="translate(286 103) rotate(-8) scale(.67)"/>
    <use :href="href('flower')" transform="translate(178 206) rotate(10) scale(.7)"/>
    <use :href="href('bud')" transform="translate(82 93) rotate(-20) scale(.78)"/>
    <use :href="href('bud')" transform="translate(169 61) rotate(26) scale(.83)"/>
    <use :href="href('bud')" transform="translate(230 48) rotate(32) scale(.78)"/>
    <use :href="href('bud')" transform="translate(282 32) rotate(38) scale(.64)"/>
    <use :href="href('bud')" transform="translate(298 69) rotate(57) scale(.63)"/>
    <path :fill="ref('petal')" class="botanical-petal-edge" d="M244 201c-12-2-16-11-14-18 11 0 15 7 14 18Zm31 26c4-10 12-14 19-11-3 10-9 14-19 11Zm-93 35c-11 1-17-4-17-11 10-3 16 2 17 11Z" opacity=".65"/>
  </g>
  </template>
</svg>
</template>
