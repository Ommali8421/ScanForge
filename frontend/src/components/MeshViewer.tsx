import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  Eye,
  RotateCw,
  Crosshair,
  ZoomIn,
  ZoomOut,
  RefreshCw,
  AlertTriangle,
  Ruler,
  Palette,
} from "lucide-react";

export type CanvasTheme = "white" | "light-grey" | "dark-slate";

interface Props {
  modelUrl?: string;
  onPointSelected?: (point: [number, number, number]) => void;
  measureMode?: boolean;
  onToggleMeasureMode?: () => void;
  pointA?: [number, number, number] | null;
  pointB?: [number, number, number] | null;
  label?: string;
  activeTab?: "textured" | "dense" | "mesh";
  onTabChange?: (tab: "textured" | "dense" | "mesh") => void;
  jobMetadata?: {
    id: string;
    scanType?: string;
    quality?: string;
  };
}

export const MeshViewer: React.FC<Props> = ({
  modelUrl,
  onPointSelected,
  measureMode = false,
  onToggleMeasureMode,
  pointA,
  pointB,
  label = "raw, uncalibrated (SfM units)",
  activeTab = "textured",
  onTabChange,
  jobMetadata,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const [wireframe, setWireframe] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  // Independent canvas theme: white (#ffffff) / light-grey (#f1f5f9) / dark slate (#090d16)
  const [canvasTheme, setCanvasTheme] = useState<CanvasTheme>("white");
  const [loadingModel, setLoadingModel] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const gridRef = useRef<THREE.GridHelper | null>(null);
  const meshGroupRef = useRef<THREE.Group | null>(null);
  const markersGroupRef = useRef<THREE.Group | null>(null);

  const initialCamPos = useRef<THREE.Vector3>(new THREE.Vector3(0, 2, 5));
  const initialTarget = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const pressedKeysRef = useRef<Set<string>>(new Set());
  const modelSpanRef = useRef<number>(6.0);

  const getCanvasColor = (theme: CanvasTheme) => {
    switch (theme) {
      case "light-grey":
        return "#f1f5f9";
      case "dark-slate":
        return "#090d16";
      case "white":
      default:
        return "#ffffff";
    }
  };

  const cycleCanvasTheme = () => {
    setCanvasTheme((prev) => {
      if (prev === "white") return "light-grey";
      if (prev === "light-grey") return "dark-slate";
      return "white";
    });
  };

  // Keyboard Event Listeners (WASD + Space/Ctrl + Shift movement with capture phase)
  useEffect(() => {
    const isMovementKey = (key: string, code: string) => {
      return (
        key === "w" || code === "keyw" ||
        key === "s" || code === "keys" ||
        key === "a" || code === "keya" ||
        key === "d" || code === "keyd" ||
        key === " " || key === "space" || code === "space" ||
        key === "control" || code === "controlleft" || code === "controlright" ||
        key === "shift" || code === "shiftleft" || code === "shiftright" ||
        key === "c" || code === "keyc" ||
        key === "arrowup" || key === "arrowdown" || key === "arrowleft" || key === "arrowright"
      );
    };

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }

      const key = e.key ? e.key.toLowerCase() : "";
      const code = e.code ? e.code.toLowerCase() : "";

      if (isMovementKey(key, code)) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
      }

      if (key) pressedKeysRef.current.add(key);
      if (code) pressedKeysRef.current.add(code);
      if (e.ctrlKey) pressedKeysRef.current.add("control");
      if (e.shiftKey) pressedKeysRef.current.add("shift");
    };

    const onKeyUp = (e: KeyboardEvent) => {
      const key = e.key ? e.key.toLowerCase() : "";
      const code = e.code ? e.code.toLowerCase() : "";

      if (key) pressedKeysRef.current.delete(key);
      if (code) pressedKeysRef.current.delete(code);
      if (!e.ctrlKey) {
        pressedKeysRef.current.delete("control");
        pressedKeysRef.current.delete("controlleft");
        pressedKeysRef.current.delete("controlright");
      }
      if (!e.shiftKey) {
        pressedKeysRef.current.delete("shift");
        pressedKeysRef.current.delete("shiftleft");
        pressedKeysRef.current.delete("shiftright");
      }
    };

    const onBlur = () => {
      pressedKeysRef.current.clear();
    };

    window.addEventListener("keydown", onKeyDown, { capture: true });
    window.addEventListener("keyup", onKeyUp, { capture: true });
    window.addEventListener("blur", onBlur);
    document.addEventListener("visibilitychange", onBlur);

    return () => {
      window.removeEventListener("keydown", onKeyDown, { capture: true });
      window.removeEventListener("keyup", onKeyUp, { capture: true });
      window.removeEventListener("blur", onBlur);
      document.removeEventListener("visibilitychange", onBlur);
    };
  }, []);

  useEffect(() => {
    if (!mountRef.current) return;
    setLoadError(null);

    // 1. Scene setup
    const scene = new THREE.Scene();
    const bgColor = getCanvasColor(canvasTheme);
    scene.background = new THREE.Color(bgColor);
    sceneRef.current = scene;

    // 2. Camera setup
    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.05, 1000);
    camera.position.copy(initialCamPos.current);
    cameraRef.current = camera;

    // 3. Renderer setup with sRGB color space
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Orbit Controls (Smooth orbit, pan, and zoom)
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.minDistance = 0.05;
    controls.maxDistance = 500;
    // Neutralize default OrbitControls key listeners to prevent fighting WASD
    controls.listenToKeyEvents = () => {};
    controls.keys = { LEFT: "", UP: "", RIGHT: "", BOTTOM: "" };
    controlsRef.current = controls;

    // 5. Lights (Full multi-source illumination for glTF PBR and unlit geometry)
    const isDarkCanvas = canvasTheme === "dark-slate";
    const hemiLight = new THREE.HemisphereLight(
      0xffffff,
      isDarkCanvas ? 0x222222 : 0xcccccc,
      1.2
    );
    hemiLight.position.set(0, 20, 0);
    scene.add(hemiLight);

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.5);
    dirLight1.position.set(5, 12, 7);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight2.position.set(-5, 8, -5);
    scene.add(dirLight2);

    const dirLight3 = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight3.position.set(0, -10, 0); // Upward bounce so ceilings and under-surfaces don't go pitch black
    scene.add(dirLight3);

    // 6. Floor Grid (Adaptive grid colors based on canvas theme)
    let gridColor1 = 0x9ca3af;
    let gridColor2 = 0xe5e7eb;
    if (canvasTheme === "dark-slate") {
      gridColor1 = 0x3b82f6;
      gridColor2 = 0x1e293b;
    } else if (canvasTheme === "light-grey") {
      gridColor1 = 0x94a3b8;
      gridColor2 = 0xe2e8f0;
    }

    const grid = new THREE.GridHelper(10, 20, gridColor1, gridColor2);
    grid.position.y = 0;
    gridRef.current = grid;
    scene.add(grid);

    // 7. Groups
    const group = new THREE.Group();
    meshGroupRef.current = group;
    scene.add(group);

    const markersGroup = new THREE.Group();
    markersGroupRef.current = markersGroup;
    scene.add(markersGroup);

    // 8. Load Model
    if (modelUrl) {
      setLoadingModel(true);
      const isPly = modelUrl.toLowerCase().endsWith(".ply");

      if (isPly) {
        const plyLoader = new PLYLoader();
        plyLoader.load(
          modelUrl,
          (geometry) => {
            while (group.children.length > 0) {
              group.remove(group.children[0]);
            }
            geometry.computeVertexNormals();
            geometry.computeBoundingBox();

            const bbox = geometry.boundingBox || new THREE.Box3();
            const size = bbox.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z) || 2.0;

            geometry.center();

            const hasVertexColors = geometry.hasAttribute("color");
            let pcdObject: THREE.Object3D;

            if (geometry.index !== null) {
              // Surface Mesh PLY
              const mat = new THREE.MeshStandardMaterial({
                vertexColors: hasVertexColors,
                color: hasVertexColors ? 0xffffff : 0x94a3b8,
                roughness: 1.0,
                metalness: 0.0,
                side: THREE.DoubleSide,
              });
              pcdObject = new THREE.Mesh(geometry, mat);
            } else {
              // Point Cloud PLY
              const pcdMat = new THREE.PointsMaterial({
                size: Math.max(0.015, maxDim * 0.005),
                vertexColors: hasVertexColors,
                color: hasVertexColors ? 0xffffff : (isDarkCanvas ? 0x38bdf8 : 0x0284c7),
              });
              pcdObject = new THREE.Points(geometry, pcdMat);
            }

            group.add(pcdObject);

            const dist = maxDim * 1.6;
            modelSpanRef.current = maxDim;
            camera.position.set(dist * 0.7, dist * 0.6, dist * 0.8);
            controls.target.set(0, 0, 0);
            controls.update();

            initialCamPos.current.copy(camera.position);
            initialTarget.current.set(0, 0, 0);
            setLoadingModel(false);
          },
          undefined,
          (err) => {
            console.error("[MeshViewer] PLYLoader failed:", err);
            const msg = (err as any)?.message || "File corrupted or unavailable";
            setLoadError(`Failed to load PLY geometry: ${msg}`);
            setLoadingModel(false);
          }
        );
      } else {
        const gltfLoader = new GLTFLoader();
        gltfLoader.setMeshoptDecoder(MeshoptDecoder);
        gltfLoader.load(
          modelUrl,
          (gltf) => {
            while (group.children.length > 0) {
              group.remove(group.children[0]);
            }
            const model = gltf.scene;

            // Fix glTF materials: ensure metalness=0, roughness=1, double-sided, sRGB color space, and normal scale
            model.traverse((child) => {
              if ((child as THREE.Mesh).isMesh) {
                const mesh = child as THREE.Mesh;
                mesh.castShadow = false;
                mesh.receiveShadow = false;
                const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
                materials.forEach((mat) => {
                  if (mat instanceof THREE.MeshStandardMaterial) {
                    mat.metalness = 0.0; // Prevent pitch-black render without HDR env map
                    mat.roughness = 1.0;
                    mat.side = THREE.DoubleSide; // Render both exterior and interior faces
                    if (mat.normalMap) {
                      mat.normalScale.set(0.45, 0.45);
                      mat.normalMap.needsUpdate = true;
                    }
                    if (mat.map) {
                      mat.map.colorSpace = THREE.SRGBColorSpace;
                      mat.map.needsUpdate = true;
                    }
                  }
                });
              }
            });

            const box = new THREE.Box3().setFromObject(model);
            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z) || 2.0;

            // Center geometry
            model.position.sub(center);
            group.add(model);

            const dist = maxDim * 1.6;
            modelSpanRef.current = maxDim;
            camera.position.set(dist * 0.7, dist * 0.6, dist * 0.8);
            controls.target.set(0, 0, 0);
            controls.update();

            initialCamPos.current.copy(camera.position);
            initialTarget.current.set(0, 0, 0);
            setLoadingModel(false);
          },
          undefined,
          (err) => {
            console.error("[MeshViewer] GLTFLoader failed:", err);
            const msg = (err as any)?.message || "File corrupted or unavailable";
            setLoadError(`Failed to load glTF model: ${msg}`);
            setLoadingModel(false);
          }
        );
      }
    } else {
      setLoadError("No 3D asset available for this job (0 artifacts registered). This reconstruction did not emit a 3D model.");
    }

    // 9. Raycasting for point selection
    const raycaster = new THREE.Raycaster();
    const mouseCoord = new THREE.Vector2();

    const handleClick = (e: MouseEvent) => {
      if (!onPointSelected) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouseCoord.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouseCoord.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouseCoord, camera);
      const intersects = raycaster.intersectObjects(group.children, true);
      if (intersects.length > 0) {
        const pt = intersects[0].point;
        onPointSelected([parseFloat(pt.x.toFixed(3)), parseFloat(pt.y.toFixed(3)), parseFloat(pt.z.toFixed(3))]);
      }
    };
    renderer.domElement.addEventListener("click", handleClick);

    // 10. Resize handler
    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // 11. Animation Loop with WASD Movement
    let animId: number;
    let lastTime = performance.now();

    const animate = () => {
      animId = requestAnimationFrame(animate);
      const now = performance.now();
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      const keys = pressedKeysRef.current;
      if (camera && keys.size > 0) {
        const viewDir = new THREE.Vector3();
        camera.getWorldDirection(viewDir);

        let forward = new THREE.Vector3(viewDir.x, 0, viewDir.z);
        if (forward.lengthSq() < 1e-4) {
          forward.set(camera.up.x, 0, camera.up.z);
        }
        if (forward.lengthSq() < 1e-4) {
          forward.set(0, 0, -1);
        } else {
          forward.normalize();
        }

        const right = new THREE.Vector3().crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();
        const worldUp = new THREE.Vector3(0, 1, 0);

        const moveDelta = new THREE.Vector3(0, 0, 0);

        // W: Forward
        if (keys.has("w") || keys.has("keyw") || keys.has("arrowup")) {
          moveDelta.add(forward);
        }
        // S: Backward
        if (keys.has("s") || keys.has("keys") || keys.has("arrowdown")) {
          moveDelta.sub(forward);
        }
        // D: Right
        if (keys.has("d") || keys.has("keyd") || keys.has("arrowright")) {
          moveDelta.add(right);
        }
        // A: Left
        if (keys.has("a") || keys.has("keya") || keys.has("arrowleft")) {
          moveDelta.sub(right);
        }
        // Space: Up (+Y)
        if (keys.has(" ") || keys.has("space")) {
          moveDelta.add(worldUp);
        }
        // CTRL / C: Down (-Y)
        if (
          keys.has("control") ||
          keys.has("controlleft") ||
          keys.has("controlright") ||
          keys.has("c") ||
          keys.has("keyc")
        ) {
          moveDelta.sub(worldUp);
        }

        if (moveDelta.lengthSq() > 1e-6) {
          moveDelta.normalize();

          let speed = Math.max(1.0, 0.25 * modelSpanRef.current);
          if (keys.has("shift") || keys.has("shiftleft") || keys.has("shiftright")) {
            speed *= 2.5;
          }
          const distance = speed * dt;
          moveDelta.multiplyScalar(distance);

          camera.position.add(moveDelta);
          if (controls && controls.target) {
            controls.target.add(moveDelta);
          }
        }
      }

      controls.autoRotate = autoRotate;
      controls.autoRotateSpeed = 2.0;
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      renderer.domElement.removeEventListener("click", handleClick);
      window.removeEventListener("resize", handleResize);
      controls.dispose();
      if (renderer.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [modelUrl, onPointSelected, canvasTheme]);

  // Update wireframe mode
  useEffect(() => {
    if (!meshGroupRef.current) return;
    meshGroupRef.current.traverse((child) => {
      if (child instanceof THREE.Mesh && child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => (m.wireframe = wireframe));
        } else {
          child.material.wireframe = wireframe;
        }
      }
    });
  }, [wireframe]);

  // Update 3D marker spheres for Point A and Point B
  useEffect(() => {
    if (!markersGroupRef.current) return;
    const group = markersGroupRef.current;
    while (group.children.length > 0) {
      group.remove(group.children[0]);
    }

    if (pointA) {
      // Point A: Vivid Crimson / Red (0xdc2626) with black outline ring
      const geoA = new THREE.SphereGeometry(0.08, 16, 16);
      const matA = new THREE.MeshBasicMaterial({ color: 0xdc2626 });
      const sphereA = new THREE.Mesh(geoA, matA);
      sphereA.position.set(pointA[0], pointA[1], pointA[2]);
      group.add(sphereA);

      const ringGeoA = new THREE.RingGeometry(0.09, 0.11, 24);
      const ringMatA = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide });
      const ringA = new THREE.Mesh(ringGeoA, ringMatA);
      ringA.position.set(pointA[0], pointA[1], pointA[2]);
      ringA.lookAt(cameraRef.current ? cameraRef.current.position : new THREE.Vector3(0, 1, 0));
      group.add(ringA);
    }

    if (pointB) {
      // Point B: Vivid Royal Blue (0x2563eb) with black outline ring
      const geoB = new THREE.SphereGeometry(0.08, 16, 16);
      const matB = new THREE.MeshBasicMaterial({ color: 0x2563eb });
      const sphereB = new THREE.Mesh(geoB, matB);
      sphereB.position.set(pointB[0], pointB[1], pointB[2]);
      group.add(sphereB);

      const ringGeoB = new THREE.RingGeometry(0.09, 0.11, 24);
      const ringMatB = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide });
      const ringB = new THREE.Mesh(ringGeoB, ringMatB);
      ringB.position.set(pointB[0], pointB[1], pointB[2]);
      ringB.lookAt(cameraRef.current ? cameraRef.current.position : new THREE.Vector3(0, 1, 0));
      group.add(ringB);

      if (pointA) {
        // High-contrast measure line
        const lineMat = new THREE.LineBasicMaterial({ color: 0x9333ea, linewidth: 3 });
        const points = [
          new THREE.Vector3(pointA[0], pointA[1], pointA[2]),
          new THREE.Vector3(pointB[0], pointB[1], pointB[2]),
        ];
        const lineGeo = new THREE.BufferGeometry().setFromPoints(points);
        const line = new THREE.Line(lineGeo, lineMat);
        group.add(line);
      }
    }
  }, [pointA, pointB]);

  // Zoom control helpers
  const handleZoom = (factor: number) => {
    if (!cameraRef.current || !controlsRef.current) return;
    const cam = cameraRef.current;
    const controls = controlsRef.current;
    const dir = new THREE.Vector3().subVectors(cam.position, controls.target);
    dir.multiplyScalar(factor);
    cam.position.copy(controls.target).add(dir);
    controls.update();
  };

  const handleResetView = () => {
    if (!cameraRef.current || !controlsRef.current) return;
    cameraRef.current.position.copy(initialCamPos.current);
    controlsRef.current.target.copy(initialTarget.current);
    controlsRef.current.update();
  };

  const isDarkCanvas = canvasTheme === "dark-slate";

  return (
    <div
      className={`relative w-full h-[520px] sm:h-[600px] rounded-3xl overflow-hidden border shadow-2xl transition-colors duration-200 ${
        isDarkCanvas
          ? "bg-[#090d16] border-zinc-800"
          : canvasTheme === "light-grey"
          ? "bg-[#f1f5f9] border-slate-300"
          : "bg-white border-slate-200"
      }`}
    >
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Explicit Error Display Overlay */}
      {loadError && (
        <div className="absolute inset-0 bg-zinc-950/90 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center z-20">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-3">
            <AlertTriangle className="w-6 h-6 text-rose-400" />
          </div>
          <h4 className="text-sm font-bold text-white mb-1">Model Unavailable in Viewer</h4>
          <p className="text-xs text-rose-300 max-w-md font-mono bg-rose-950/40 border border-rose-900/50 p-3 rounded-2xl mb-3">
            {loadError}
          </p>
          <p className="text-[11px] text-zinc-400 max-w-sm">
            ScanForge real-mode pipelines display only verified 3D assets. Facades and dummy boxes are strictly disabled.
          </p>
        </div>
      )}

      {/* TOP-LEFT HUD OVERLAY: Mode Switcher & Metadata Pill */}
      <div className="absolute top-4 left-4 flex flex-col sm:flex-row items-start sm:items-center gap-2 z-10">
        {onTabChange && (
          <div className="flex items-center space-x-1 bg-zinc-950/80 backdrop-blur-md p-1 rounded-2xl border border-zinc-800/80 text-xs shadow-xl">
            <button
              onClick={() => onTabChange("textured")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                activeTab === "textured"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Textured Mesh
            </button>
            <button
              onClick={() => onTabChange("dense")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                activeTab === "dense"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Dense Cloud (PLY)
            </button>
            <button
              onClick={() => onTabChange("mesh")}
              className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                activeTab === "mesh"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Raw Geometry
            </button>
          </div>
        )}

        <div className="flex items-center gap-1.5">
          {jobMetadata && (
            <span className="px-2.5 py-1.5 rounded-xl bg-zinc-950/80 backdrop-blur-md border border-zinc-800/80 text-[11px] font-mono text-cyan-300 shadow-md">
              {jobMetadata.id.slice(0, 8)}
            </span>
          )}
          <span className="px-3 py-1.5 rounded-xl bg-zinc-950/80 backdrop-blur-md border border-zinc-800/80 text-[11px] font-mono text-zinc-300 shadow-md">
            {label}
          </span>
          {loadingModel && (
            <span className="px-2.5 py-1.5 rounded-xl bg-cyan-500/20 border border-cyan-500/40 text-[11px] text-cyan-300 font-mono font-bold animate-pulse shadow-md">
              Loading 3D asset...
            </span>
          )}
        </div>
      </div>

      {/* BOTTOM-CENTER FLOATING DOCK */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center space-x-1 bg-zinc-950/85 backdrop-blur-md p-1.5 rounded-2xl border border-zinc-800 text-xs shadow-2xl z-10">
        {/* Reset Camera View */}
        <button
          onClick={handleResetView}
          className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title="Reset Camera View"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        {/* Zoom Controls */}
        <button
          onClick={() => handleZoom(0.8)}
          className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title="Zoom In (+)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleZoom(1.25)}
          className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title="Zoom Out (-)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-5 mx-0.5 bg-zinc-800" />

        {/* Wireframe Toggle */}
        <button
          onClick={() => setWireframe(!wireframe)}
          className={`px-2.5 py-1.5 rounded-xl flex items-center space-x-1.5 transition-all ${
            wireframe
              ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/30"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800"
          }`}
          title="Toggle wireframe topology view"
        >
          <Eye className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Wireframe</span>
        </button>

        {/* Auto-turntable rotate */}
        <button
          onClick={() => setAutoRotate(!autoRotate)}
          className={`p-2 rounded-xl transition-all ${
            autoRotate
              ? "bg-cyan-600 text-white shadow-md shadow-cyan-600/30"
              : "text-zinc-400 hover:text-white hover:bg-zinc-800"
          }`}
          title="Toggle auto-orbit turntable"
        >
          <RotateCw className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-5 mx-0.5 bg-zinc-800" />

        {/* Canvas Background Theme (White / Light-Grey / Dark-Slate) */}
        <button
          onClick={cycleCanvasTheme}
          className="px-2.5 py-1.5 rounded-xl flex items-center space-x-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title={`Canvas Theme: ${canvasTheme} (Click to cycle White / Light-Grey / Dark-Slate)`}
        >
          <Palette className="w-3.5 h-3.5 text-amber-400" />
          <span className="capitalize font-mono text-[11px] hidden sm:inline">
            {canvasTheme.replace("-", " ")}
          </span>
        </button>

        {/* Measure & Calibrate Tool Toggle */}
        {onToggleMeasureMode && (
          <>
            <div className="w-[1px] h-5 mx-0.5 bg-zinc-800" />
            <button
              onClick={onToggleMeasureMode}
              className={`px-3 py-1.5 rounded-xl flex items-center space-x-1.5 font-bold transition-all ${
                measureMode
                  ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/30 animate-pulse"
                  : "bg-indigo-600/80 hover:bg-indigo-600 text-white"
              }`}
              title="Activate Measure & Scale Calibration Tool"
            >
              <Ruler className="w-3.5 h-3.5" />
              <span>Measure & Calibrate</span>
            </button>
          </>
        )}
      </div>

      {/* Navigation HUD Pill (WASD / Fly Mode) */}
      {!measureMode && (
        <div
          className="absolute top-4 right-4 z-10 hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-zinc-950/80 backdrop-blur-md border border-zinc-800 text-[11px] font-mono text-zinc-400 shadow-xl select-none"
          title="W: Forward • S: Backward • A: Left • D: Right • Space: Up • Ctrl: Down • Shift: Boost • Left-Drag: Orbit"
        >
          <span className="text-cyan-400 font-bold">WASD</span>
          <span>Move</span>
          <span className="text-zinc-600">•</span>
          <span className="text-cyan-400 font-bold">Space/Ctrl</span>
          <span>Up/Down</span>
          <span className="text-zinc-600">•</span>
          <span className="text-cyan-400 font-bold">Shift</span>
          <span>Boost</span>
        </div>
      )}

      {/* Floating Instructions Banner (when measure mode is active) */}
      {measureMode && (
        <div className="absolute top-4 right-4 z-10">
          <div className="bg-emerald-950/90 backdrop-blur-md border border-emerald-500/40 text-emerald-200 px-3.5 py-2 rounded-2xl text-xs flex items-center gap-2 shadow-xl">
            <Crosshair className="w-4 h-4 text-emerald-400 animate-spin" />
            <span className="font-semibold">
              {!pointA
                ? "Step 1: Click Point A on 3D geometry"
                : !pointB
                ? "Step 2: Click Point B on 3D geometry"
                : "Points selected! Enter real distance below"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
