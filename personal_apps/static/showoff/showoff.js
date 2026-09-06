(() => {
  'use strict';
  const canvas = document.querySelector('#universe');
  const notice = document.querySelector('#notice');
  const gl = canvas.getContext('webgl', { alpha: true, antialias: false, depth: false, powerPreference: 'low-power' });
  function showNotice(message) { notice.textContent = message; notice.hidden = false; }
  if (!gl) {
    showNotice('This little universe needs WebGL. Try a browser with hardware acceleration enabled.');
    document.querySelectorAll('button, input').forEach(el => { el.disabled = true; });
    return;
  }
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let paused = reducedMotion.matches;
  const mobile = innerWidth < 700;
  const count = mobile ? 9500 : 18000;
  const stars = 650;
  const total = count + stars;
  const position = new Float32Array(total * 3);
  const target = new Float32Array(count * 3);
  const velocity = new Float32Array(count * 3);
  const colors = new Float32Array(total * 3);
  const sizes = new Float32Array(total);
  const random = new Float32Array(count * 4);
  let seed = 42;
  function rand() { seed = (Math.imul(seed, 1664525) + 1013904223) | 0; return (seed >>> 0) / 4294967296; }
  for (let i = 0; i < random.length; i++) random[i] = rand();
  const vertex = `
    attribute vec3 aPosition;
    attribute vec3 aColor;
    attribute float aSize;
    uniform vec2 uResolution;
    uniform vec2 uRotation;
    uniform float uZoom;
    uniform float uPixelRatio;
    uniform float uCenter;
    varying vec3 vColor;
    void main() {
      vec3 p = aPosition;
      float sy = sin(uRotation.x), cy = cos(uRotation.x);
      float sx = sin(uRotation.y), cx = cos(uRotation.y);
      p = vec3(p.x*cy+p.z*sy, p.y, -p.x*sy+p.z*cy);
      p = vec3(p.x, p.y*cx-p.z*sx, p.y*sx+p.z*cx);
      float perspective = 4.8 / max(1.0, 4.8-p.z);
      float scale = min(uResolution.x * .28, uResolution.y * .29) * uZoom;
      vec2 screen = vec2(p.x, -p.y) * perspective * scale;
      screen += vec2(uResolution.x * uCenter, uResolution.y * .475);
      gl_Position = vec4(screen / uResolution * vec2(2., -2.) + vec2(-1., 1.), 0., 1.);
      gl_PointSize = clamp(aSize * perspective * uPixelRatio, 1.0, 48.0);
      vColor = aColor * clamp(.8+p.z*.18,.35,1.3);
    }`;
  const fragment = `
    precision mediump float;
    varying vec3 vColor;
    void main() {
      float r = length(gl_PointCoord-.5)*2.;
      if(r>1.) discard;
      float glow = exp(-r*r*5.)*.22 + exp(-r*r*65.)*.9;
      gl_FragColor = vec4(vColor * glow, glow);
    }`;
  function shader(type, source) {
    const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  let program;
  try {
    program = gl.createProgram();
    gl.attachShader(program, shader(gl.VERTEX_SHADER, vertex));
    gl.attachShader(program, shader(gl.FRAGMENT_SHADER, fragment));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('Unable to link particle renderer');
  } catch (error) { showNotice('The particle renderer could not start. Reload or try another browser.'); return; }
  gl.useProgram(program);
  gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
  const uniforms = Object.fromEntries(['uResolution','uRotation','uZoom','uPixelRatio','uCenter'].map(name => [name,gl.getUniformLocation(program,name)]));
  function buffer(name, data, width, usage) {
    const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,b);
    gl.bufferData(gl.ARRAY_BUFFER,data,usage);
    const location = gl.getAttribLocation(program,name);
    gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location,width,gl.FLOAT,false,0,0);
    return b;
  }
  for (let i = 0; i < total; i++) {
    sizes[i] = i < count ? 3.5 + rand()*6 : 2 + rand()*4;
    if (i >= count) {
      position[i*3] = (rand()-.5)*9;
      position[i*3+1] = (rand()-.5)*6;
      position[i*3+2] = -2-rand()*3;
      colors.set([.25,.36,.48],i*3);
    }
  }
  const posBuffer = buffer('aPosition',position,3,gl.DYNAMIC_DRAW);
  const colorBuffer = buffer('aColor',colors,3,gl.DYNAMIC_DRAW);
  buffer('aSize',sizes,1,gl.STATIC_DRAW);
  let width, height, pixelRatio;
  function resize() {
    width = canvas.clientWidth; height = canvas.clientHeight;
    pixelRatio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width*pixelRatio); canvas.height = Math.round(height*pixelRatio);
    gl.viewport(0,0,canvas.width,canvas.height);
    gl.uniform2f(uniforms.uResolution,width,height);
    gl.uniform1f(uniforms.uPixelRatio,pixelRatio);
    gl.uniform1f(uniforms.uCenter,width < 700 ? .5 : .56);
    render();
  }
  let shape = 'galaxy', angle = -.25, tilt = .44, zoom = 1;
  let targetTilt = .44, targetAngle = -.25;
  let held = false, dragging = false, pointerX = 0, pointerY = 0, holdTime = 0;
  let lastTime = 0, elapsed = 0, frame = 0, disposed = false;
  const sceneInfo = {
    galaxy: ['01 / 04','Spiral galaxy','A little order. A lot of beautiful chaos.',.44],
    saturn: ['02 / 04','Saturn, reimagined','A world you can hold. Rings you can unravel.',.18],
    helix: ['03 / 04','The shape of life','Two threads. A thousand possibilities.',.06],
    text: ['04 / 04','Written in the stars','Your words. The same tiny universe.',0],
  };
  function textPoints() {
    const off = document.createElement('canvas'); off.width = 1100; off.height = 230;
    const ctx = off.getContext('2d', { willReadFrequently:true });
    const value = document.querySelector('#words').value.trim() || 'MICHI';
    ctx.font = '900 180px Arial';
    const scale = Math.min(1,1000/Math.max(1,ctx.measureText(value).width));
    ctx.font = `900 ${180*scale}px Arial`;
    ctx.textAlign='center'; ctx.textBaseline='middle'; ctx.fillStyle='white'; ctx.fillText(value,550,120);
    const data = ctx.getImageData(0,0,1100,230).data;
    const points=[];
    for(let y=0;y<230;y+=2) for(let x=0;x<1100;x+=2) if(data[(y*1100+x)*4+3]>128) points.push([x,y]);
    if (!points.length) points.push([550,115]);
    return points;
  }
  function setShape(next, immediate=false) {
    shape=next;
    const text = next==='text' ? textPoints() : null;
    const info=sceneInfo[next];
    document.querySelector('#scene-number').textContent=info[0];
    document.querySelector('#scene-title').textContent=info[1];
    document.querySelector('#scene-description').textContent=info[2];
    document.querySelectorAll('[data-shape]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.shape===next)));
    targetTilt=info[3]; targetAngle=next==='text'?0:angle;
    for(let i=0;i<count;i++) {
      const a=random[i*4], b=random[i*4+1], c=random[i*4+2], d=random[i*4+3];
      let x,y,z,r,t; let color;
      if(next==='galaxy') {
        r=Math.pow(a,.65)*1.62;
        t=(i%4)*Math.PI/2+r*3.8+(b-.5)*(.25+r*.4);
        x=Math.cos(t)*r; z=Math.sin(t)*r; y=(c-.5)*(.065+.19*(1-r/1.65));
        if(i%5===0) { const sphere=Math.acos(2*b-1); x=Math.sin(sphere)*Math.cos(c*6.283)*r*.34; z=Math.sin(sphere)*Math.sin(c*6.283)*r*.34; y=Math.cos(sphere)*r*.21; }
        color=r<.4?[1,.72,.44]:i%3===0?[.58,.43,1]:[.24,.73,1];
      } else if(next==='saturn') {
        if(i<count*.52) { t=b*6.283; const phi=Math.acos(2*a-1); r=.61+(.5-d)*.028; x=r*Math.sin(phi)*Math.cos(t);y=r*Math.cos(phi);z=r*Math.sin(phi)*Math.sin(t); color=[.95,.67+.15*Math.sin(y*45),.42]; }
        else { r=.88+a*.66; if(r>1.18&&r<1.25)r+=.09; t=b*6.283; x=r*Math.cos(t);z=r*Math.sin(t);y=(c-.5)*.018; const yy=y*.9-z*.38; z=y*.38+z*.9; y=yy; color=i%4===0?[.44,.73,.86]:[.85,.72,.55]; }
      } else if(next==='helix') {
        y=(a-.5)*2.35; t=y*6.8+(i%2)*Math.PI;
        r=.43;
        if(i%5===0){r=(b-.5)*.86;t=Math.round((y+1.2)*12)/12*6.8-1.2*6.8;y=Math.round((y+1.2)*12)/12-1.2;}
        x=Math.cos(t)*r+(c-.5)*.055;z=Math.sin(t)*r+(d-.5)*.055;
        color=i%2===0?[.34,.9,.85]:[.85,.47,.95];
      } else {
        const p=text[Math.floor(a*text.length)];
        x=(p[0]-550)/370; y=(115-p[1])/370;z=(c-.5)*.095;
        color=[.48+b*.48,.77+b*.2,.95];
      }
      target.set([x,y,z],i*3);
      const intensity=.6+d*.65;
      colors.set(color.map(v=>v*intensity),i*3);
      if(immediate||paused) {position.set([x,y,z],i*3);velocity.fill(0,i*3,i*3+3);}
    }
    if(paused){angle=targetAngle;tilt=targetTilt;}
    gl.bindBuffer(gl.ARRAY_BUFFER,colorBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,colors);
    render();
  }
  function render() {
    if(!width || gl.isContextLost())return;
    gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(uniforms.uRotation,angle,tilt);gl.uniform1f(uniforms.uZoom,zoom);
    gl.bindBuffer(gl.ARRAY_BUFFER,posBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,position);
    gl.drawArrays(gl.POINTS,0,total);
  }
  function tick(time) {
    frame=0;
    if(paused||document.hidden||disposed)return;
    const dt=Math.min((time-(lastTime||time))/16.667,2);lastTime=time;elapsed+=dt*.016667;
    if(!dragging)targetAngle+=shape==='text'?0:dt*.0013;
    angle+=(targetAngle-angle)*Math.min(1,.075*dt);tilt+=(targetTilt-tilt)*Math.min(1,.075*dt);
    const scatter=held && time-holdTime>160;
    for(let i=0;i<count;i++) {
      const k=i*3;
      for(let axis=0;axis<3;axis++) {
        const j=k+axis;
        const drift=shape==='text'?0:Math.sin(elapsed*.6+random[i*4]*20+axis)*.009;
        velocity[j]+=(target[j]+drift-position[j])*.009*dt;
        if(scatter)velocity[j]+=position[j]*.009*dt+(random[i*4+axis]-.5)*.007*dt;
        velocity[j]*=Math.pow(.91,dt);
        position[j]+=velocity[j]*dt;
      }
    }
    render();frame=requestAnimationFrame(tick);
  }
  function resumeLoop() {lastTime=0;if(!frame&&!paused&&!document.hidden&&!disposed)frame=requestAnimationFrame(tick);}
  function updatePause() {
    const b=document.querySelector('#pause');b.textContent=paused?'Resume motion':'Pause motion';b.setAttribute('aria-pressed',String(paused));
    if(paused){cancelAnimationFrame(frame);frame=0;held=false;}else resumeLoop();
  }
  document.querySelectorAll('[data-shape]').forEach(b=>b.addEventListener('click',()=>setShape(b.dataset.shape)));
  document.querySelector('#text-form').addEventListener('submit',e=>{e.preventDefault();setShape('text');document.querySelector('#words').blur();});
  document.querySelector('#explode').addEventListener('click',()=>{
    if(paused){showNotice('Resume motion to set off a supernova.');setTimeout(()=>notice.hidden=true,2500);return;}
    for(let i=0;i<count;i++) {
      const k=i*3;const norm=Math.hypot(position[k],position[k+1],position[k+2])||1;
      for(let axis=0;axis<3;axis++)velocity[k+axis]+=position[k+axis]/norm*(.09+random[i*4]*.12)+(random[i*4+axis]-.5)*.075;
    }
  });
  document.querySelector('#pause').addEventListener('click',()=>{paused=!paused;updatePause();});
  reducedMotion.addEventListener('change',e=>{paused=e.matches;updatePause();if(paused)setShape(shape,true);});
  canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;held=true;dragging=true;pointerX=e.clientX;pointerY=e.clientY;holdTime=performance.now();canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{
    if(!dragging)return;
    const dx=e.clientX-pointerX,dy=e.clientY-pointerY;
    targetAngle+=dx*.005;targetTilt=Math.max(-1.3,Math.min(1.3,targetTilt+dy*.005));
    if(Math.abs(dx)+Math.abs(dy)>3)holdTime=performance.now();
    pointerX=e.clientX;pointerY=e.clientY;
    if(paused){angle=targetAngle;tilt=targetTilt;render();}
  });
  function release(){held=false;dragging=false;}
  canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('lostpointercapture',release);window.addEventListener('blur',release);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.55,Math.min(1.8,zoom-e.deltaY*.001));render();},{passive:false});
  document.addEventListener('visibilitychange',()=>{release();if(document.hidden){cancelAnimationFrame(frame);frame=0;}else resumeLoop();});
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();disposed=true;cancelAnimationFrame(frame);showNotice('The graphics context was interrupted. Reload to bring your universe back.');});
  window.addEventListener('pagehide',()=>{cancelAnimationFrame(frame);frame=0;});
  window.addEventListener('pageshow',resumeLoop);
  window.addEventListener('resize',resize);
  document.querySelector('#particle-count').textContent=`${count.toLocaleString('en-US')} particles · live`;
  setShape('galaxy',true);resize();updatePause();resumeLoop();
})();
