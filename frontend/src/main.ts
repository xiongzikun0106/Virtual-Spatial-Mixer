import "./style.css";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

type Transport = { time: number; playing: boolean; duration: number };
type TrackRow = {
  id: number;
  name: string;
  color: [number, number, number];
  muted: boolean;
  solo: boolean;
  priority: number;
  rec_armed: boolean;
  waveform: number[];
  keyframes: [number, number, number, number][];
  segments: { motion_type: string }[];
  track_duration: number;
};
type Snapshot = {
  transport: Transport;
  tracks: TrackRow[];
  positions: Record<string, [number, number, number]>;
  glows: Record<string, number>;
};

type PyApi = {
  get_snapshot: () => Promise<Snapshot>;
  import_audio: () => Promise<{ errors: string[]; snapshot: Snapshot }>;
  export_audio: () => Promise<{ ok: boolean; message?: string; snapshot: Snapshot }>;
  play_pause: () => Promise<{ playing: boolean; snapshot: Snapshot }>;
  stop: () => Promise<{ snapshot: Snapshot }>;
  seek: (t: number) => Promise<{ snapshot: Snapshot }>;
  set_mute: (tid: number, v: boolean) => Promise<{ snapshot: Snapshot }>;
  set_solo: (tid: number, v: boolean) => Promise<{ snapshot: Snapshot }>;
  set_priority: (tid: number, v: number) => Promise<{ snapshot: Snapshot }>;
  set_coord: (tid: number, x: number, y: number, z: number) => Promise<{ snapshot: Snapshot }>;
  stamp_keyframe: (tid: number) => Promise<{ snapshot: Snapshot }>;
  remove_track: (tid: number) => Promise<{ snapshot: Snapshot }>;
  set_track_rec: (tid: number, active: boolean) => Promise<{ snapshot: Snapshot }>;
  r_key_down: () => Promise<{ snapshot: Snapshot }>;
  r_key_up: () => Promise<{ snapshot: Snapshot }>;
};

function api(): PyApi {
  const w = window as unknown as { pywebview?: { api: PyApi } };
  if (!w.pywebview?.api) {
    throw new Error("需要 pywebview 环境（python main.py --webview）");
  }
  return w.pywebview.api;
}

async function snap(): Promise<Snapshot> {
  return api().get_snapshot();
}

const app = document.querySelector<HTMLDivElement>("#app")!;

app.innerHTML = `
<header class="toolbar">
  <button type="button" id="btn-import">Import</button>
  <button type="button" id="btn-play">Play</button>
  <button type="button" id="btn-stop">Stop</button>
  <button type="button" id="btn-export">Export</button>
  <span class="time" id="time-label">0:00.00</span>
  <span class="hint">按住 R 键录制（需先勾选轨道的 ● REC）</span>
</header>
<div class="main">
  <aside id="track-list"></aside>
  <div class="viewport-wrap">
    <canvas id="c3d"></canvas>
    <div class="scrub-wrap">
      <div id="scrubber" class="scrubber"><div id="playhead" class="playhead"></div></div>
    </div>
  </div>
</div>
`;

const btnImport = document.querySelector("#btn-import")!;
const btnPlay = document.querySelector("#btn-play")!;
const btnStop = document.querySelector("#btn-stop")!;
const btnExport = document.querySelector("#btn-export")!;
const timeLabel = document.querySelector("#time-label")!;
const trackListEl = document.querySelector("#track-list")!;
const scrubber = document.querySelector("#scrubber")!;
const playhead = document.querySelector("#playhead")!;
const canvas = document.querySelector("#c3d") as HTMLCanvasElement;

let lastSnapshot: Snapshot | null = null;
let trackIdsRendered: string = "";

function fmtTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

function applyTransport(s: Snapshot) {
  lastSnapshot = s;
  timeLabel.textContent = fmtTime(s.transport.time);
  const w = s.transport.duration > 0 ? s.transport.time / s.transport.duration : 0;
  playhead.style.left = `${Math.min(100, Math.max(0, w * 100))}%`;
  btnPlay.textContent = s.transport.playing ? "Pause" : "Play";
}

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a1a);
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 500);
camera.position.set(8, 6, 10);
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 0.35));
const dir = new THREE.DirectionalLight(0xffffff, 1.1);
dir.position.set(4, 10, 6);
scene.add(dir);

const grid = new THREE.GridHelper(30, 30, 0x333333, 0x222222);
scene.add(grid);

const sphereMeshes = new Map<number, THREE.Mesh>();
const sphereGeom = new THREE.SphereGeometry(0.35, 28, 28);

function setSize() {
  const wrap = canvas.parentElement!;
  const w = wrap.clientWidth;
  const h = wrap.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
}
window.addEventListener("resize", setSize);

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const dragPlane = new THREE.Plane();
const planeHit = new THREE.Vector3();
let dragMesh: THREE.Mesh | null = null;
let dragThrottle = 0;

function tidOf(mesh: THREE.Mesh): number {
  return mesh.userData.tid as number;
}

function onPointerDown(ev: PointerEvent) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const objs = [...sphereMeshes.values()];
  const hits = raycaster.intersectObjects(objs, false);
  if (hits.length > 0) {
    dragMesh = hits[0].object as THREE.Mesh;
    dragPlane.setFromNormalAndCoplanarPoint(
      new THREE.Vector3(0, 1, 0),
      dragMesh.position,
    );
    canvas.setPointerCapture(ev.pointerId);
  }
}

function onPointerMove(ev: PointerEvent) {
  if (!dragMesh) return;
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  if (raycaster.ray.intersectPlane(dragPlane, planeHit)) {
    dragMesh.position.copy(planeHit);
    const now = performance.now();
    if (now - dragThrottle > 80) {
      dragThrottle = now;
      const tid = tidOf(dragMesh);
      const { x, y, z } = dragMesh.position;
      void api().set_coord(tid, x, y, z).then((r) => applyAll(r.snapshot));
    }
  }
}

function onPointerUp(ev: PointerEvent) {
  if (dragMesh) {
    const tid = tidOf(dragMesh);
    const { x, y, z } = dragMesh.position;
    void api().set_coord(tid, x, y, z).then((r) => applyAll(r.snapshot));
  }
  dragMesh = null;
  try {
    canvas.releasePointerCapture(ev.pointerId);
  } catch {
    /* ignore */
  }
}

canvas.addEventListener("pointerdown", onPointerDown);
canvas.addEventListener("pointermove", onPointerMove);
canvas.addEventListener("pointerup", onPointerUp);

function applyThree(s: Snapshot) {
  const ids = new Set(s.tracks.map((t) => t.id));
  for (const [tid, mesh] of sphereMeshes) {
    if (!ids.has(tid)) {
      scene.remove(mesh);
      sphereMeshes.delete(tid);
    }
  }
  for (const tr of s.tracks) {
    let mesh = sphereMeshes.get(tr.id);
    if (!mesh) {
      const [r, g, b] = tr.color;
      const rf = r / 255;
      const gf = g / 255;
      const bf = b / 255;
      const mat = new THREE.MeshStandardMaterial({
        color: new THREE.Color(rf, gf, bf),
        metalness: 0.2,
        roughness: 0.45,
        emissive: new THREE.Color(rf, gf, bf),
        emissiveIntensity: 0.15,
      });
      mesh = new THREE.Mesh(sphereGeom, mat);
      mesh.userData.tid = tr.id;
      scene.add(mesh);
      sphereMeshes.set(tr.id, mesh);
    }
    const pos = s.positions[String(tr.id)];
    if (pos) {
      mesh.position.set(pos[0], pos[1], pos[2]);
    }
    const g = s.glows[String(tr.id)] ?? 0.3;
    const mat = mesh.material as THREE.MeshStandardMaterial;
    mat.emissiveIntensity = 0.1 + Math.min(1, g) * 0.85;
  }
}

function drawWaveform(canvasEl: HTMLCanvasElement, samples: number[]) {
  const ctx = canvasEl.getContext("2d")!;
  const w = canvasEl.width;
  const h = canvasEl.height;
  ctx.fillStyle = "#141414";
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = "#3a5a7a";
  ctx.beginPath();
  const n = samples.length;
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * w;
    const y = h / 2 - samples[i] * (h / 2 - 2);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
}

function renderTrackList(s: Snapshot) {
  const sig = s.tracks.map((t) => t.id).join(",");
  if (sig === trackIdsRendered && trackListEl.childElementCount > 0) {
    syncTrackControls(s);
    return;
  }
  trackIdsRendered = sig;
  trackListEl.innerHTML = "";
  for (const tr of s.tracks) {
    const buf = document.createElement("div");
    buf.className = "track-card";
    buf.dataset.tid = String(tr.id);
    const pos = s.positions[String(tr.id)] ?? [0, 0, 0];
    buf.innerHTML = `
      <div class="track-head">
        <span class="track-name">${escapeHtml(tr.name)}</span>
        <button type="button" class="btn-x" data-remove="${tr.id}">×</button>
      </div>
      <canvas class="wf" width="280" height="40" data-wf="${tr.id}"></canvas>
      <div class="row">
        <label><input type="checkbox" id="m-${tr.id}" ${tr.muted ? "checked" : ""} /> M</label>
        <label><input type="checkbox" id="s-${tr.id}" ${tr.solo ? "checked" : ""} /> S</label>
        <label><input type="checkbox" id="r-${tr.id}" ${tr.rec_armed ? "checked" : ""} /> ●REC</label>
        <label class="pr">Pri <input type="number" id="p-${tr.id}" value="${tr.priority}" style="width:3rem" /></label>
      </div>
      <div class="row coords">
        <label>X <input type="number" step="0.01" id="cx-${tr.id}" value="${pos[0].toFixed(2)}" /></label>
        <label>Y <input type="number" step="0.01" id="cy-${tr.id}" value="${pos[1].toFixed(2)}" /></label>
        <label>Z <input type="number" step="0.01" id="cz-${tr.id}" value="${pos[2].toFixed(2)}" /></label>
      </div>
      <div class="row">
        <button type="button" class="btn-sm" data-kf="${tr.id}">+KF</button>
        <span class="kf-count">${tr.keyframes.length} keyframes</span>
      </div>
    `;
    trackListEl.appendChild(buf);
    const wf = buf.querySelector<HTMLCanvasElement>(`[data-wf="${tr.id}"]`)!;
    drawWaveform(wf, tr.waveform);

    buf.querySelector(`[data-remove="${tr.id}"]`)!.addEventListener("click", () => {
      void api().remove_track(tr.id).then((r) => applyAll(r.snapshot));
    });
    buf.querySelector(`[data-kf="${tr.id}"]`)!.addEventListener("click", () => {
      void api().stamp_keyframe(tr.id).then((r) => applyAll(r.snapshot));
    });

    const bindChk = (sel: string, fn: (v: boolean) => Promise<{ snapshot: Snapshot }>) => {
      buf.querySelector(sel)!.addEventListener("change", (e) => {
        const v = (e.target as HTMLInputElement).checked;
        void fn(v).then((r) => applyAll(r.snapshot));
      });
    };
    bindChk(`#m-${tr.id}`, (v) => api().set_mute(tr.id, v));
    bindChk(`#s-${tr.id}`, (v) => api().set_solo(tr.id, v));
    bindChk(`#r-${tr.id}`, (v) => api().set_track_rec(tr.id, v));

    buf.querySelector(`#p-${tr.id}`)!.addEventListener("change", (e) => {
      const v = parseInt((e.target as HTMLInputElement).value, 10) || 0;
      void api().set_priority(tr.id, v).then((r) => applyAll(r.snapshot));
    });

    const bindCoord = (axis: string) => {
      buf.querySelector(`#c${axis}-${tr.id}`)!.addEventListener("change", () => {
        const cx = parseFloat((buf.querySelector(`#cx-${tr.id}`) as HTMLInputElement).value);
        const cy = parseFloat((buf.querySelector(`#cy-${tr.id}`) as HTMLInputElement).value);
        const cz = parseFloat((buf.querySelector(`#cz-${tr.id}`) as HTMLInputElement).value);
        void api().set_coord(tr.id, cx, cy, cz).then((r) => applyAll(r.snapshot));
      });
    };
    bindCoord("x");
    bindCoord("y");
    bindCoord("z");
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

function syncTrackControls(s: Snapshot) {
  for (const tr of s.tracks) {
    const buf = trackListEl.querySelector<HTMLElement>(`[data-tid="${tr.id}"]`);
    if (!buf) continue;
    const mute = buf.querySelector<HTMLInputElement>(`#m-${tr.id}`);
    const solo = buf.querySelector<HTMLInputElement>(`#s-${tr.id}`);
    const rec = buf.querySelector<HTMLInputElement>(`#r-${tr.id}`);
    const pr = buf.querySelector<HTMLInputElement>(`#p-${tr.id}`);
    const cx = buf.querySelector<HTMLInputElement>(`#cx-${tr.id}`);
    const cy = buf.querySelector<HTMLInputElement>(`#cy-${tr.id}`);
    const cz = buf.querySelector<HTMLInputElement>(`#cz-${tr.id}`);
    const kfCount = buf.querySelector(".kf-count");
    const pos = s.positions[String(tr.id)];
    if (mute) mute.checked = tr.muted;
    if (solo) solo.checked = tr.solo;
    if (rec) rec.checked = tr.rec_armed;
    if (pr && document.activeElement !== pr) pr.value = String(tr.priority);
    if (
      pos &&
      cx &&
      cy &&
      cz &&
      document.activeElement !== cx &&
      document.activeElement !== cy &&
      document.activeElement !== cz
    ) {
      cx.value = pos[0].toFixed(2);
      cy.value = pos[1].toFixed(2);
      cz.value = pos[2].toFixed(2);
    }
    if (kfCount) kfCount.textContent = `${tr.keyframes.length} keyframes`;
  }
}

function applyAll(s: Snapshot) {
  applyTransport(s);
  applyThree(s);
  renderTrackList(s);
  syncTrackControls(s);
}

btnImport.addEventListener("click", () => {
  void api()
    .import_audio()
    .then((r) => {
      if (r.errors.length) alert(r.errors.join("\n"));
      applyAll(r.snapshot);
    })
    .catch((e) => alert(String(e)));
});

btnPlay.addEventListener("click", () => {
  void api()
    .play_pause()
    .then((r) => applyAll(r.snapshot))
    .catch((e) => alert(String(e)));
});

btnStop.addEventListener("click", () => {
  void api()
    .stop()
    .then((r) => applyAll(r.snapshot))
    .catch((e) => alert(String(e)));
});

btnExport.addEventListener("click", () => {
  void api()
    .export_audio()
    .then((r) => {
      if (!r.ok) alert(r.message ?? "export failed");
      else applyAll(r.snapshot);
    })
    .catch((e) => alert(String(e)));
});

scrubber.addEventListener("click", (e) => {
  if (!lastSnapshot) return;
  const rect = scrubber.getBoundingClientRect();
  const x = (e.clientX - rect.left) / rect.width;
  const t = x * lastSnapshot.transport.duration;
  void api()
    .seek(t)
    .then((r) => applyAll(r.snapshot))
    .catch((err) => alert(String(err)));
});

window.addEventListener("keydown", (e) => {
  if (e.repeat) return;
  if (e.code === "KeyR") {
    void api()
      .r_key_down()
      .then((r) => applyAll(r.snapshot))
      .catch(() => {});
  }
});
window.addEventListener("keyup", (e) => {
  if (e.code === "KeyR") {
    void api()
      .r_key_up()
      .then((r) => applyAll(r.snapshot))
      .catch(() => {});
  }
});

function tickLoop() {
  void snap()
    .then((s) => {
      applyTransport(s);
      applyThree(s);
      syncTrackControls(s);
    })
    .catch(() => {});
}

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}

setSize();
animate();
setInterval(tickLoop, 50);

snap()
  .then((s) => applyAll(s))
  .catch((e) => {
    trackListEl.innerHTML = `<p class="err">${escapeHtml(String(e))}</p>`;
  });
