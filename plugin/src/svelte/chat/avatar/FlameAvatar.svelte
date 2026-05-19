<script lang="ts">
  import { onMount, onDestroy } from 'svelte';

  let { state = 'peek' }: { state?: 'peek' | 'look' | 'think' | 'happy' | 'answer' | 'confused' } = $props();

  let canvas: HTMLCanvasElement;
  let ctx: CanvasRenderingContext2D | null;
  let animationFrameId: number;
  let startTime: number | null = null;

  // ═══════════════════════════════════════════
  // COLORS
  // ═══════════════════════════════════════════
  const FC = {
    red:   { outer:'#8B1A10', mid:'#C04A28', core:'#F5C5A0', hi:'#FDE8D8', spark:'#C04A28', dot:'#EEDDD8' },
    blue:  { outer:'#1A3A5C', mid:'#3A7AB0', core:'#A8CCE8', hi:'#D8E8F5', spark:'#3A7AB0', dot:'#D8E0EE' },
    green: { outer:'#194F1B', mid:'#3BA34F', core:'#B3D8A7', hi:'#D0E9DD', spark:'#3BA34F', dot:'#E6EEE2' },
    pink:  { outer:'#8B2050', mid:'#C04A78', core:'#F5C5D8', hi:'#FDE8F0', spark:'#C04A78', dot:'#EED8E2' },
  };
  const STATE_COLOR: Record<string, keyof typeof FC> = { peek:'red', look:'green', think:'blue', happy:'pink', answer:'red', confused:'blue' };
  
  let currentFlameColor: keyof typeof FC = 'red';

  // ═══════════════════════════════════════════
  // GRID
  // ═══════════════════════════════════════════
  const PX = 20; // Scale factor for pixel art
  const CANVAS_SIZE = 720;

  function px(x: number, y: number, c?: string) {
    if (c && ctx) {
      ctx.fillStyle = c;
      ctx.fillRect(Math.round(x) * PX, Math.round(y) * PX, PX, PX);
    }
  }

  function fillRect(x: number, y: number, w: number, h: number, c: string) {
    for (let dy = 0; dy < h; dy++) {
      for (let dx = 0; dx < w; dx++) {
        px(x + dx, y + dy, c);
      }
    }
  }

  // ═══════════════════════════════════════════
  // BACKGROUND
  // ═══════════════════════════════════════════
  function drawBg() {
    if (!ctx) return;
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);
  }

  // ═══════════════════════════════════════════
  // FLAME CHARACTER
  // ═══════════════════════════════════════════
  const FX = 18, FY = 18; // Center

  const SLICES = {
    outer: [[-12,1],[-11,2],[-10,3],[-9,5],[-8,6],[-7,7],[-6,7],[-5,8],[-4,8],[-3,8],[-2,8],[-1,8],[0,8],[1,8],[2,7],[3,7],[4,6],[5,5],[6,5]],
    mid:   [[-9,1],[-8,3],[-7,5],[-6,5],[-5,6],[-4,6],[-3,6],[-2,6],[-1,6],[0,6],[1,6],[2,5],[3,5],[4,3]],
    core:  [[-6,1],[-5,3],[-4,4],[-3,5],[-2,5],[-1,5],[0,5],[1,4],[2,3],[3,2]],
    hi:    [[-4,2],[-3,3],[-2,3],[-1,2]]
  } as const;

  function drawFlameBody(cx: number, cy: number, C: any, flicker: number) {
    for (const key of ['outer','mid','core','hi'] as const) {
      const color = C[key];
      for (const [dy, hw] of SLICES[key]) {
        const fw = Math.round(Math.sin(flicker*0.08 + dy*0.4)*0.6);
        for (let x = -(hw+fw); x <= (hw+fw); x++) px(cx+x, cy+dy, color);
        
        if (key === 'outer' && hw > 1) {
          const topBoost = dy < -6 ? 0.3 : 0;
          if (Math.sin(dy*2.7+flicker*0.05)>-topBoost) px(cx-hw-fw-1, cy+dy, color);
          if (Math.sin(dy*1.9+flicker*0.07+1)>-topBoost) px(cx+hw+fw+1, cy+dy, color);
          if (dy < -8 && Math.sin(dy*3.5+flicker*0.06)>-0.2) {
            px(cx-hw-fw-2, cy+dy, color);
            px(cx+hw+fw+2, cy+dy, color);
          }
        }
      }
    }
  }

  function drawTip(tx: number, ty: number, h: number, c1: string, c2: string, c3?: string) {
    for(let i=0; i<h; i++) {
      const w = Math.max(0, Math.floor((h-i)*0.55));
      for(let j=-w; j<=w; j++) {
        const c = i===0 ? c1 : (i<h*0.3 ? (c3||c2) : c2);
        px(tx+j, ty-i, c);
      }
    }
  }

  function drawFlameTips(cx: number, cy: number, C: any, flicker: number) {
    const sw1=Math.sin(flicker*0.13), sw2=Math.sin(flicker*0.17+1.5), sw3=Math.sin(flicker*0.11+3.0);
    const sw4=Math.sin(flicker*0.09+4.0);
    const h1=3+Math.round(Math.abs(Math.sin(flicker*0.09))*2);
    const h2=5+Math.round(Math.abs(Math.sin(flicker*0.07))*2);
    const h3=3+Math.round(Math.abs(Math.sin(flicker*0.1+2))*2);
    const h4=2+Math.round(Math.abs(Math.sin(flicker*0.12+1))*2);

    drawTip(cx-4+Math.round(sw1*1), cy-11, h1, C.outer, C.mid);
    drawTip(cx+Math.round(sw2*0.5), cy-12, h2, C.outer, C.mid, C.core);
    drawTip(cx+4+Math.round(sw3*-1), cy-10, h3, C.outer, C.mid);
    drawTip(cx-2+Math.round(sw4*0.5), cy-13, h4, C.outer, C.mid);
  }

  function drawEmbers(cx: number, cy: number, C: any, f: number) {
    if (!ctx) return;
    const positions = [
      {ox:-10, oy:-9, ph:0},  {ox:10, oy:-6, ph:1.5},
      {ox:-7, oy:-13, ph:3},  {ox:9, oy:-11, ph:4.5},
      {ox:-11, oy:-4, ph:2.5},{ox:11, oy:-9, ph:5.0}
    ];
    for (const e of positions) {
      const vis = Math.sin(f*0.06+e.ph);
      if (vis > 0) {
        const yoff = Math.round(Math.sin(f*0.04+e.ph)*2);
        ctx.globalAlpha = vis * 0.7;
        px(cx+e.ox, cy+e.oy+yoff, C.outer);
        px(cx+e.ox, cy+e.oy+yoff-1, C.mid);
        ctx.globalAlpha = 1;
      }
    }
  }

  function drawLog(cx: number, by: number) {
    fillRect(cx-9,by,19,3,'#654321');
    fillRect(cx-8,by,17,1,'#7A5A35');
    fillRect(cx-7,by+1,15,1,'#6B4E2F');
    px(cx-5,by+2,'#3A2510');
    px(cx-1,by+2,'#3A2510');
    px(cx+4,by+2,'#3A2510');
    px(cx+1,by+1,'#3A2510');
    px(cx-10,by,'#7A5A35'); px(cx-10,by+1,'#654321'); px(cx-10,by+2,'#543219');
    px(cx+10,by,'#7A5A35'); px(cx+10,by+1,'#654321'); px(cx+10,by+2,'#543219');
  }

  function drawFlameEyes(cx: number, ey: number, type: string) {
    const lx=cx-3, rx=cx+2;
    switch(type) {
      case 'forward':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey+1,'#000'); px(rx,ey+1,'#000');
        break;
      case 'left':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx,ey+1,'#000'); px(rx,ey+1,'#000');
        break;
      case 'right':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey+1,'#000'); px(rx+1,ey+1,'#000');
        break;
      case 'up':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey,'#000'); px(rx,ey,'#000');
        break;
      case 'happy':
        px(lx,ey+1,'#000'); px(lx+1,ey,'#000');
        px(rx,ey,'#000'); px(rx+1,ey+1,'#000');
        break;
      case 'blink':
        fillRect(lx,ey+1,2,1,'#000'); fillRect(rx,ey+1,2,1,'#000');
        break;
      case 'wide':
        fillRect(lx,ey,2,2,'#FFF'); fillRect(rx,ey,2,2,'#FFF');
        px(lx+1,ey,'#000'); px(rx,ey,'#000');
        break;
    }
  }

  function drawFlameMouth(cx: number, my: number, type: string) {
    switch(type) {
      case 'neutral': fillRect(cx-1,my,3,1,'#333'); break;
      case 'smile':
        px(cx-2,my-1,'#333'); fillRect(cx-1,my,3,1,'#333'); px(cx+2,my-1,'#333');
        break;
      case 'open': fillRect(cx-1,my,3,2,'#333'); px(cx,my+1,'#554'); break;
      case 'small': px(cx,my,'#333'); break;
      case 'o':
        fillRect(cx-1,my,3,1,'#333'); px(cx-1,my+1,'#333'); px(cx+1,my+1,'#333');
        break;
    }
  }

  function drawFlame(cx: number, cy: number, opts: any = {}) {
    if (!ctx) return;
    const { color='red', eyes='forward', mouth='neutral',
            flicker=0, bounce=0, tilt=0, offsetY=0 } = opts;
    const C = FC[color as keyof typeof FC];
    const y = cy + Math.round(bounce) + Math.round(offsetY);
    const t = Math.round(tilt);

    ctx.globalAlpha=0.15;
    for(const [dy,hw] of SLICES.outer){
      for(let x=-(hw+3);x<=(hw+3);x++) px(cx+t+x, y+dy, C.hi);
    }
    ctx.globalAlpha=1;

    drawLog(cx+t, y+6);
    drawFlameTips(cx+t, y, C, flicker);
    drawFlameBody(cx+t, y, C, flicker);
    drawEmbers(cx+t, y, C, flicker);
    drawFlameEyes(cx+t, y-3, eyes);
    drawFlameMouth(cx+t, y+1, mouth);
  }

  // ═══════════════════════════════════════════
  // EFFECTS
  // ═══════════════════════════════════════════
  let particles: any[] = [];
  function addP(x: number, y: number, c: string, vx?: number, vy?: number) {
    particles.push({x,y,vx:vx||(Math.random()-.5)*.5,vy:vy||(-Math.random()*.5-.2),life:1,c});
  }
  function tickP() {
    if (!ctx) return;
    for(let i=particles.length-1;i>=0;i--){
      const p=particles[i]; p.x+=p.vx; p.y+=p.vy; p.vy+=0.02; p.life-=0.018;
      if(p.life<=0){particles.splice(i,1);continue;}
      if(p.life>0.1){
        ctx.globalAlpha=Math.min(1,p.life*1.5);
        px(Math.round(p.x),Math.round(p.y),p.c);
        ctx.globalAlpha=1;
      }
    }
  }

  function drawBubble(bx: number, by: number, text: string) {
    if (!ctx) return;
    const tw=text.length+2;
    for(let y=0;y<3;y++) for(let x=0;x<tw;x++){
      if((y===0||y===2)&&(x===0||x===tw-1))continue;
      px(bx+x,by+y,(y===0||y===2||x===0||x===tw-1)?'#CCC':'#FFF');
    }
    px(bx+1,by+3,'#CCC');
    ctx.fillStyle='#666';ctx.font='bold 12px Courier New';ctx.textAlign='left';ctx.textBaseline='top';
    ctx.fillText(text,(bx+1)*PX+4,by*PX+7);
  }

  function drawQuestion(qx: number, qy: number) {
    if (!ctx) return;
    ctx.fillStyle='#DD6236';ctx.font='bold 28px Courier New';ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText('?',qx*PX+PX/2,qy*PX+PX/2);
  }

  function drawDots(dx: number, dy: number, count: number, alpha: number) {
    if (!ctx) return;
    ctx.globalAlpha=Math.max(0,Math.min(1,alpha));ctx.fillStyle='#999';ctx.font='bold 16px Courier New';
    ctx.textAlign='left';ctx.textBaseline='top';
    for(let i=0;i<count;i++) ctx.fillText('.',(dx+i*2)*PX,dy*PX);
    ctx.globalAlpha=1;
  }

  function drawHeartPixel(hx: number, hy: number, c: string) {
    px(hx,hy,c);px(hx+2,hy,c);
    px(hx-1,hy+1,c);px(hx,hy+1,c);px(hx+1,hy+1,c);px(hx+2,hy+1,c);
    px(hx,hy+2,c);px(hx+1,hy+2,c);px(hx+1,hy+3,c);
  }

  // ═══════════════════════════════════════════
  // EASING
  // ═══════════════════════════════════════════
  function easeOut(t: number){return 1-Math.pow(1-t,3);}
  function easeInOut(t: number){return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;}
  function lerp(a: number, b: number, t: number){return a+(b-a)*t;}

  // ═══════════════════════════════════════════
  // STATE RENDERERS
  // ═══════════════════════════════════════════
  function renderPeek(f: number, t: number, pt: number) {
    const C = FC.red;
    let offsetY=0, bounce=0, eyes='forward';

    if (pt < 0.45) {
      offsetY = lerp(24, 0, easeOut(pt/0.45));
    } else if (pt < 0.7) {
      const p = (pt-0.45)/0.25;
      bounce = Math.sin(p*Math.PI*3)*(1-p)*2;
      eyes = p<0.2 ? 'blink' : p<0.4 ? 'happy' : 'forward';
    } else {
      bounce = Math.sin(pt*Math.PI*2)*0.3;
      eyes = 'forward';
    }

    drawFlame(FX, FY, {
      color:'red', eyes, mouth: pt>0.6?'smile':'neutral',
      flicker:f, bounce:Math.round(bounce), offsetY:Math.round(offsetY),
    });

    if(pt<0.45 && f%4===0) addP(FX-3+Math.random()*7, FY+12+Math.round(offsetY), C.spark);
    if(pt>0.5 && pt<0.7 && f%5===0) addP(FX-5+Math.random()*11, FY-10, C.spark);
    tickP();
  }

  function renderLook(f: number, t: number, pt: number) {
    const cycle = (pt*4)%4;
    let eyes='forward', tilt=0;
    if(cycle<1){const p=cycle;eyes=p<0.3?'forward':'left';tilt=p<0.3?0:lerp(0,-1.2,easeOut(Math.min(1,(p-0.3)/0.4)));}
    else if(cycle<2){const p=cycle-1;eyes=p<0.5?'left':'forward';tilt=lerp(-1.2,0,easeInOut(p));}
    else if(cycle<3){const p=cycle-2;eyes=p<0.3?'forward':'right';tilt=p<0.3?0:lerp(0,1.2,easeOut(Math.min(1,(p-0.3)/0.4)));}
    else{const p=cycle-3;eyes=p<0.5?'right':'forward';tilt=lerp(1.2,0,easeInOut(p));}

    drawFlame(FX, FY, {color:'green', eyes, mouth:'neutral', flicker:f, tilt:Math.round(tilt*10)/10});
    if(Math.sin(f*0.05+1)>0.95) drawFlameEyes(FX+Math.round(tilt), FY-3, 'blink');
    tickP();
  }

  function renderThink(f: number, t: number, pt: number) {
    const C = FC.blue;
    const eyes = Math.sin(f*0.04)>0.9?'blink':'up';
    const tilt = Math.sin(f*0.08)*0.6;
    const dotCount = Math.floor((pt*3)%4);

    drawFlame(FX, FY, {color:'blue', eyes, mouth:'small', flicker:f, tilt:Math.round(tilt*10)/10});
    drawDots(FX-1, FY-16, dotCount+1, 0.5+Math.sin(f*0.1)*0.3);
    if(f%15<3&&pt>0.2) addP(FX-3+Math.random()*7, FY-10, C.spark);
    tickP();
  }

  function renderHappy(f: number, t: number, pt: number) {
    if (!ctx) return;
    const C = FC.pink;
    const bounce = Math.sin(pt*Math.PI*5)*1.5;

    drawFlame(FX, FY, {color:'pink', eyes:'happy', mouth:'smile', flicker:f, bounce:Math.round(bounce)});

    if(pt>0.15){
      const h1y=FY-10-Math.round(Math.sin(f*0.1)*3);
      ctx.globalAlpha=Math.max(0.3,Math.sin(pt*Math.PI));
      drawHeartPixel(FX+11, h1y, C.core);
      if(pt>0.4) drawHeartPixel(FX-12, FY-8-Math.round(Math.sin(f*0.08)*2), C.mid);
      ctx.globalAlpha=1;
    }
    if(f%6===0){addP(FX-5+Math.random()*11,FY-10+Math.random()*3,C.spark);addP(FX-5+Math.random()*11,FY-10+Math.random()*3,C.mid);}
    tickP();
  }

  function renderAnswer(f: number, t: number, pt: number) {
    const mouthOpen = Math.sin(f*0.5)>0;
    drawFlame(FX, FY, {
      color:'red',
      eyes: Math.sin(f*0.05)>0.93?'blink':'forward',
      mouth: mouthOpen?'open':'neutral', flicker:f,
    });
    if(pt>0.1) drawBubble(FX+11, FY-16, '.'.repeat(Math.floor(f/10)%4)||' ');
    if(f%12===0) addP(FX+Math.random()*6-3, FY-10, FC.red.core);
    tickP();
  }

  function renderConfused(f: number, t: number, pt: number) {
    if (!ctx) return;
    const C = FC.blue;
    const tilt = Math.sin(f*0.1)*1.5;
    const wobble = Math.round(Math.sin(f*0.2)*0.5);
    const eyes = Math.sin(f*0.08)>0.85?'blink':'wide';

    drawFlame(FX, FY+wobble, {color:'blue', eyes, mouth:'o', flicker:f, tilt:Math.round(tilt*10)/10});

    if(Math.sin(f*0.1)>-0.3){
      ctx.globalAlpha=0.6+Math.sin(f*0.15)*0.3;
      drawQuestion(FX-8,FY-16);if(pt>0.3) drawQuestion(FX+10,FY-14);
      ctx.globalAlpha=1;
    }
    if(f%30<5){const sy=FY-2+Math.round((f%30)/5*2);px(FX+9,sy,'#88BBDD');px(FX+9,sy+1,'#88BBDD');}
    tickP();
  }

  const RENDERERS = {
    peek: renderPeek,
    look: renderLook,
    think: renderThink,
    happy: renderHappy,
    answer: renderAnswer,
    confused: renderConfused
  };

  const FPS = 30;
  const STATE_DUR = { peek:2.5, look:6, think:4, happy:3, answer:3, confused:3 };

  function render(f: number) {
    const dur = STATE_DUR[state] || 3;
    const total = FPS * dur;
    const t = f / total;
    const pt = ((t % 1) + 1) % 1;
    
    drawBg();
    const renderer = RENDERERS[state];
    if (renderer) renderer(f, t, pt);
  }

  function loop(ts: number) {
    if (!startTime) startTime = ts;
    const elapsed = (ts - startTime) / 1000;
    const dur = STATE_DUR[state] || 3;
    const loopSec = elapsed % dur;
    const frame = Math.floor(loopSec * FPS);
    
    if (loopSec < 0.05) particles = [];
    render(frame);
    animationFrameId = requestAnimationFrame(loop);
  }

  $effect(() => {
    currentFlameColor = STATE_COLOR[state] || 'red';
    particles = [];
  });

  onMount(() => {
    ctx = canvas.getContext('2d');
    animationFrameId = requestAnimationFrame(loop);
  });

  onDestroy(() => {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
    }
  });
</script>

<canvas
  bind:this={canvas}
  width="720"
  height="720"
  style="width: 100%; height: 100%; image-rendering: pixelated; image-rendering: crisp-edges;"
></canvas>
