import React, { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { MeshoptDecoder } from "three/examples/jsm/libs/meshopt_decoder.module.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
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
  Maximize2,
  Minimize2,
  Footprints,
  Sliders,
  Compass,
} from "lucide-react";

export type CanvasTheme = "white" | "light-grey" | "dark-slate";

export interface AlignedCamera {
  filename?: string;
  image_id?: number;
  position: [number, number, number];
  forward: [number, number, number];
  up?: [number, number, number];
  is_first_frame?: boolean;
}

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
  const outerWrapperRef = useRef<HTMLDivElement>(null);
  const mountRef = useRef<HTMLDivElement>(null);

  const [wireframe, setWireframe] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const [canvasTheme, setCanvasTheme] = useState<CanvasTheme>("dark-slate");
  const [loadingModel, setLoadingModel] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Fullscreen 3D World Mode
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isFullscreenFallback, setIsFullscreenFallback] = useState(false);

  // Navigation Mode: Orbit vs First-Person Walk
  const [navMode, setNavMode] = useState<"orbit" | "walk">("orbit");
  const [isPointerLocked, setIsPointerLocked] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState(1.0);

  // Aligned cameras for First-Frame (Frame 0) spawn
  const [alignedCameras, setAlignedCameras] = useState<AlignedCamera[]>([]);
  const [firstFrameCamera, setFirstFrameCamera] = useState<AlignedCamera | null>(null);

  // Active Keypad HUD feedback state
  const [activeHudKeys, setActiveHudKeys] = useState<{ [key: string]: boolean }>({});

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
  const navModeRef = useRef<"orbit" | "walk">("orbit");
  const speedMultiplierRef = useRef(1.0);
  const yawRef = useRef(0);
  const pitchRef = useRef(0);
  const isMouseDownRef = useRef(false);
  const lastMousePosRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    navModeRef.current = navMode;
  }, [navMode]);

  useEffect(() => {
    speedMultiplierRef.current = speedMultiplier;
  }, [speedMultiplier]);

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
      if (prev === "dark-slate") return "white";
      if (prev === "white") return "light-grey";
      return "dark-slate";
    });
  };

  // Fullscreen 3D World Mode Toggle
  const toggleFullscreen = useCallback(() => {
    const el = outerWrapperRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      if (el.requestFullscreen) {
        el.requestFullscreen().catch(() => {
          setIsFullscreenFallback((prev) => !prev);
        });
      } else {
        setIsFullscreenFallback((prev) => !prev);
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
      setIsFullscreenFallback(false);
    }
  }, []);

  useEffect(() => {
    const handleFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
      if (!document.fullscreenElement) {
        setIsFullscreenFallback(false);
      }
    };
    document.addEventListener("fullscreenchange", handleFsChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFsChange);
    };
  }, []);

  // Fetch aligned cameras if jobMetadata id exists
  useEffect(() => {
    if (!jobMetadata?.id) return;
    let active = true;
    fetch(`/api/jobs/${jobMetadata.id}/artifacts/cameras_aligned.json`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (active && data) {
          if (data.cameras && Array.isArray(data.cameras)) {
            setAlignedCameras(data.cameras);
          }
          if (data.first_frame_camera) {
            setFirstFrameCamera(data.first_frame_camera);
          } else if (data.cameras && data.cameras.length > 0) {
            setFirstFrameCamera(data.cameras[0]);
          }
        }
      })
      .catch((e) => {
        console.debug("cameras_aligned.json not available:", e);
      });
    return () => {
      active = false;
    };
  }, [jobMetadata?.id]);

  // Helper to neutralize OrbitControls key events so WASD never conflicts
  const neutralizeOrbitControlsKeys = (controls: OrbitControls | null) => {
    if (!controls) return;
    try {
      if ((controls as any)._domElementKeyEvents) {
        (controls as any).stopListenToKeyEvents?.();
      }
    } catch (_) {}
    try {
      controls.listenToKeyEvents = () => {};
      controls.keys = { LEFT: "", UP: "", RIGHT: "", BOTTOM: "" };
      (controls as any).handleKeyDown = () => {};
      (controls as any).enableKeys = false;
    } catch (_) {}
  };

  // Spawn at exact First Video Frame position and look direction (F1)
  const spawnAtFirstFrame = useCallback(() => {
    const cam = cameraRef.current;
    const controls = controlsRef.current;
    if (!cam) return;
    neutralizeOrbitControlsKeys(controls);

    const targetCam = firstFrameCamera || (alignedCameras.length > 0 ? alignedCameras[0] : null);
    if (targetCam) {
      const pos = targetCam.position;
      const fwd = targetCam.forward;
      cam.position.set(pos[0], pos[1], pos[2]);

      const fx = fwd[0];
      const fy = fwd[1];
      const fz = fwd[2];
      const initialYaw = Math.atan2(-fx, -fz);
      const initialPitch = Math.asin(THREE.MathUtils.clamp(fy, -0.98, 0.98));

      yawRef.current = initialYaw;
      pitchRef.current = initialPitch;

      cam.rotation.order = "YXZ";
      cam.rotation.set(initialPitch, initialYaw, 0, "YXZ");
      cam.updateMatrixWorld(true);

      const lookDir = new THREE.Vector3(fx, fy, fz).normalize();
      if (controls?.target) {
        controls.target.copy(cam.position).addScaledVector(lookDir, 2.5);
      }
    } else {
      cam.position.set(0, 1.4, 0);
      yawRef.current = 0;
      pitchRef.current = 0;
      cam.rotation.order = "YXZ";
      cam.rotation.set(0, 0, 0, "YXZ");
      if (controls?.target) {
        controls.target.set(0, 1.3, 3.0);
      }
    }

    if (navModeRef.current === "walk") {
      if (controls) {
        controls.enabled = false;
        if (!(controls as any)._sfOrigUpdate) {
          (controls as any)._sfOrigUpdate = controls.update.bind(controls);
        }
        controls.update = () => false;
      }
    } else {
      if (controls) {
        if ((controls as any)._sfOrigUpdate) {
          controls.update = (controls as any)._sfOrigUpdate;
        }
        controls.enabled = true;
        controls.update?.();
      }
    }
  }, [firstFrameCamera, alignedCameras]);

  // Toggle between Orbit and First-Person Walk Mode
  const toggleNavMode = useCallback(() => {
    const nextMode = navMode === "orbit" ? "walk" : "orbit";
    const controls = controlsRef.current;
    const cam = cameraRef.current;

    if (nextMode === "walk") {
      neutralizeOrbitControlsKeys(controls);
      if (controls) {
        controls.enabled = false;
        if (!(controls as any)._sfOrigUpdate) {
          (controls as any)._sfOrigUpdate = controls.update.bind(controls);
        }
        controls.update = () => false;
      }

      if (cam) {
        const viewDir = new THREE.Vector3();
        cam.getWorldDirection(viewDir);
        yawRef.current = Math.atan2(-viewDir.x, -viewDir.z);
        pitchRef.current = Math.asin(THREE.MathUtils.clamp(viewDir.y, -0.98, 0.98));
        cam.rotation.order = "YXZ";
        cam.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");
        cam.updateMatrixWorld(true);
      }

      // If switching to walk mode and near starting state, spawn at frame 0
      if (firstFrameCamera && cam && cam.position.distanceTo(initialCamPos.current) < 0.1) {
        spawnAtFirstFrame();
      }

      setNavMode("walk");
      navModeRef.current = "walk";
    } else {
      if (document.pointerLockElement) {
        document.exitPointerLock?.();
      }

      if (controls && cam) {
        if ((controls as any)._sfOrigUpdate) {
          controls.update = (controls as any)._sfOrigUpdate;
        }
        const viewDir = new THREE.Vector3();
        cam.getWorldDirection(viewDir);
        const targetDist = Math.max(1.0, 0.25 * modelSpanRef.current);
        controls.target.copy(cam.position).addScaledVector(viewDir, targetDist);
        controls.enabled = true;
        controls.update?.();
      }

      setNavMode("orbit");
      navModeRef.current = "orbit";
    }
  }, [navMode, firstFrameCamera, spawnAtFirstFrame]);

  // Pointer lock change listener
  useEffect(() => {
    const handlePointerLockChange = () => {
      const locked = !!document.pointerLockElement && document.pointerLockElement === rendererRef.current?.domElement;
      setIsPointerLocked(locked);
    };
    document.addEventListener("pointerlockchange", handlePointerLockChange);
    return () => {
      document.removeEventListener("pointerlockchange", handlePointerLockChange);
    };
  }, []);

  // Keyboard Event Listeners (WASD + Space/Ctrl/Shift with Input Guard)
  useEffect(() => {
    const isMovementKey = (key: string, code: string) => {
      return (
        key === "w" || code === "keyw" ||
        key === "s" || code === "keys" ||
        key === "a" || code === "keya" ||
        key === "d" || code === "keyd" ||
        key === " " || key === "space" || code === "space" ||
        key === "e" || code === "keye" ||
        key === "q" || code === "keyq" ||
        key === "control" || code === "controlleft" || code === "controlright" ||
        key === "shift" || code === "shiftleft" || code === "shiftright" ||
        key === "alt" || code === "altleft" || code === "altright" ||
        key === "c" || code === "keyc" ||
        key === "arrowup" || key === "arrowdown" || key === "arrowleft" || key === "arrowright"
      );
    };

    const onKeyDown = (e: KeyboardEvent) => {
      // 1. Input Box Safety First: never steal key events when typing into calibration inputs
      const target = e.target as HTMLElement | null;
      const activeEl = document.activeElement as HTMLElement | null;
      const isInput = (el: HTMLElement | null) =>
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (isInput(target) || isInput(activeEl)) {
        return;
      }

      const key = e.key ? e.key.toLowerCase() : "";
      const code = e.code ? e.code.toLowerCase() : "";

      if (code === "keyf" && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        toggleFullscreen();
        return;
      }
      if (code === "f1") {
        e.preventDefault();
        spawnAtFirstFrame();
        return;
      }

      if (isMovementKey(key, code)) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
      }

      if (key) pressedKeysRef.current.add(key);
      if (code) pressedKeysRef.current.add(code);
      if (e.ctrlKey) pressedKeysRef.current.add("control");
      if (e.shiftKey) pressedKeysRef.current.add("shift");
      if (e.altKey) pressedKeysRef.current.add("alt");

      // HUD keypad visual feedback
      const hudKey = code.startsWith("key") ? code.slice(3) : key === " " ? " " : key;
      if (hudKey) {
        setActiveHudKeys((prev) => ({ ...prev, [hudKey]: true }));
      }
    };

    const onKeyUp = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const activeEl = document.activeElement as HTMLElement | null;
      const isInput = (el: HTMLElement | null) =>
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
      if (isInput(target) || isInput(activeEl)) {
        return;
      }

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
      if (!e.altKey) {
        pressedKeysRef.current.delete("alt");
        pressedKeysRef.current.delete("altleft");
        pressedKeysRef.current.delete("altright");
      }

      const hudKey = code.startsWith("key") ? code.slice(3) : key === " " ? " " : key;
      if (hudKey) {
        setActiveHudKeys((prev) => ({ ...prev, [hudKey]: false }));
      }
    };

    const onBlur = () => {
      pressedKeysRef.current.clear();
      setActiveHudKeys({});
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
  }, [toggleFullscreen, spawnAtFirstFrame]);

  // Three.js Scene Setup & Render Loop
  useEffect(() => {
    if (!mountRef.current) return;
    setLoadError(null);

    // 1. Scene setup
    const scene = new THREE.Scene();
    const bgColor = getCanvasColor(canvasTheme);
    scene.background = new THREE.Color(bgColor);
    sceneRef.current = scene;

    // 2. Camera setup
    const width = mountRef.current.clientWidth || 800;
    const height = mountRef.current.clientHeight || 600;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.05, 1000);
    camera.position.copy(initialCamPos.current);
    cameraRef.current = camera;

    // 3. Renderer setup with sRGB color space
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Studio Environment Lighting with PMREMGenerator + RoomEnvironment
    let envTexture: THREE.Texture | null = null;
    try {
      const pmrem = new THREE.PMREMGenerator(renderer);
      const roomEnv = new RoomEnvironment();
      envTexture = pmrem.fromScene(roomEnv, 0.04).texture;
      scene.environment = envTexture;
      (scene as any).environmentIntensity = 0.65;
      roomEnv.dispose();
      pmrem.dispose();
    } catch (e) {
      console.warn("[MeshViewer] RoomEnvironment setup fallback:", e);
    }

    // 5. Orbit Controls (Smooth orbit, pan, and zoom)
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;
    controls.minDistance = 0.05;
    controls.maxDistance = 500;
    neutralizeOrbitControlsKeys(controls);
    controlsRef.current = controls;

    // 6. Lights (Full multi-source illumination for glTF PBR and unlit geometry)
    const isDarkCanvas = canvasTheme === "dark-slate";
    const hemiLight = new THREE.HemisphereLight(
      0xffffff,
      isDarkCanvas ? 0x222222 : 0xcccccc,
      1.1
    );
    hemiLight.position.set(0, 20, 0);
    scene.add(hemiLight);

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.4);
    dirLight1.position.set(5, 12, 7);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.9);
    dirLight2.position.set(-5, 8, -5);
    scene.add(dirLight2);

    const dirLight3 = new THREE.DirectionalLight(0xffffff, 0.7);
    dirLight3.position.set(0, -10, 0);
    scene.add(dirLight3);

    // 7. Floor Grid (Adaptive grid colors based on canvas theme)
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

    // 8. Groups
    const group = new THREE.Group();
    meshGroupRef.current = group;
    scene.add(group);

    const markersGroup = new THREE.Group();
    markersGroupRef.current = markersGroup;
    scene.add(markersGroup);

    // 9. Load Model
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
              const mat = new THREE.MeshStandardMaterial({
                vertexColors: hasVertexColors,
                color: hasVertexColors ? 0xffffff : 0x94a3b8,
                roughness: 0.85,
                metalness: 0.0,
                side: THREE.DoubleSide,
              });
              pcdObject = new THREE.Mesh(geometry, mat);
            } else {
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

            // Fix glTF materials: ensure metalness=0, roughness=0.9, double-sided, sRGB color space, and normal scale
            model.traverse((child) => {
              if ((child as THREE.Mesh).isMesh) {
                const mesh = child as THREE.Mesh;
                mesh.castShadow = false;
                mesh.receiveShadow = false;
                const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
                materials.forEach((mat) => {
                  if (mat instanceof THREE.MeshStandardMaterial) {
                    mat.metalness = 0.0;
                    mat.roughness = Math.max(0.7, mat.roughness ?? 0.85);
                    mat.side = THREE.DoubleSide;
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

    // 10. Pointer Lock & Mouse Look for Walk Mode + Point Selection for Calibration
    const raycaster = new THREE.Raycaster();
    const mouseCoord = new THREE.Vector2();

    const handleCanvasMouseDown = (e: MouseEvent) => {
      if (e.button === 0) {
        isMouseDownRef.current = true;
        lastMousePosRef.current = { x: e.clientX, y: e.clientY };
      }
    };

    const handleCanvasMouseUp = () => {
      isMouseDownRef.current = false;
    };

    const handleCanvasMouseMove = (e: MouseEvent) => {
      if (navModeRef.current === "walk") {
        let dx = 0;
        let dy = 0;
        if (document.pointerLockElement === renderer.domElement) {
          dx = e.movementX;
          dy = e.movementY;
        } else if (isMouseDownRef.current) {
          dx = e.clientX - lastMousePosRef.current.x;
          dy = e.clientY - lastMousePosRef.current.y;
          lastMousePosRef.current = { x: e.clientX, y: e.clientY };
        }

        if (dx !== 0 || dy !== 0) {
          const sensitivity = 0.0022;
          yawRef.current -= dx * sensitivity;
          pitchRef.current -= dy * sensitivity;
          const maxPitch = (85 * Math.PI) / 180;
          pitchRef.current = Math.max(-maxPitch, Math.min(maxPitch, pitchRef.current));

          camera.rotation.order = "YXZ";
          camera.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");
          camera.updateMatrixWorld(true);

          const lookDir = new THREE.Vector3(
            -Math.sin(yawRef.current) * Math.cos(pitchRef.current),
            Math.sin(pitchRef.current),
            -Math.cos(yawRef.current) * Math.cos(pitchRef.current)
          ).normalize();
          controls.target.copy(camera.position).addScaledVector(lookDir, 2.0);
        }
      }
    };

    const handleClick = (e: MouseEvent) => {
      if (navModeRef.current === "walk" && !measureMode) {
        if (!document.pointerLockElement) {
          renderer.domElement.requestPointerLock?.();
        }
      }

      if (!onPointSelected || !measureMode) return;
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

    const domEl = renderer.domElement;
    domEl.addEventListener("mousedown", handleCanvasMouseDown);
    window.addEventListener("mouseup", handleCanvasMouseUp);
    domEl.addEventListener("mousemove", handleCanvasMouseMove);
    domEl.addEventListener("click", handleClick);

    // 11. Resize handling with ResizeObserver
    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    };

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    if (mountRef.current) {
      resizeObserver.observe(mountRef.current);
    }
    window.addEventListener("resize", handleResize);

    // 12. Unkillable 60-144 FPS Animation Loop with WASD Movement
    let animId: number;
    let lastTime = performance.now();

    const animate = (now: number) => {
      // Unkillable: schedule at top of tick before checking readiness
      animId = requestAnimationFrame(animate);
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      if (!cameraRef.current) return;
      const cam = cameraRef.current;
      const keys = pressedKeysRef.current;

      if (keys.size > 0) {
        const viewDir = new THREE.Vector3();
        cam.getWorldDirection(viewDir);

        let forwardXZ = new THREE.Vector3(viewDir.x, 0, viewDir.z);
        if (forwardXZ.lengthSq() < 1e-4) {
          forwardXZ.set(cam.up.x, 0, cam.up.z);
        }
        if (forwardXZ.lengthSq() < 1e-4) {
          forwardXZ.set(0, 0, -1);
        } else {
          forwardXZ.normalize();
        }

        const rightXZ = new THREE.Vector3().crossVectors(forwardXZ, new THREE.Vector3(0, 1, 0)).normalize();
        const worldUp = new THREE.Vector3(0, 1, 0);

        const moveDelta = new THREE.Vector3(0, 0, 0);

        // W / Up: Forward
        if (keys.has("w") || keys.has("keyw") || keys.has("arrowup")) {
          moveDelta.add(forwardXZ);
        }
        // S / Down: Backward
        if (keys.has("s") || keys.has("keys") || keys.has("arrowdown")) {
          moveDelta.sub(forwardXZ);
        }
        // D / Right: Right
        if (keys.has("d") || keys.has("keyd") || keys.has("arrowright")) {
          moveDelta.add(rightXZ);
        }
        // A / Left: Left
        if (keys.has("a") || keys.has("keya") || keys.has("arrowleft")) {
          moveDelta.sub(rightXZ);
        }
        // Space / E: Up (+Y)
        if (keys.has(" ") || keys.has("space") || keys.has("e") || keys.has("keye")) {
          moveDelta.add(worldUp);
        }
        // CTRL / C / Q: Down (-Y)
        if (
          keys.has("control") ||
          keys.has("controlleft") ||
          keys.has("controlright") ||
          keys.has("c") ||
          keys.has("keyc") ||
          keys.has("q") ||
          keys.has("keyq")
        ) {
          moveDelta.sub(worldUp);
        }

        if (moveDelta.lengthSq() > 1e-6) {
          moveDelta.normalize();

          let speed = Math.max(1.0, 0.22 * modelSpanRef.current) * speedMultiplierRef.current;
          if (keys.has("shift") || keys.has("shiftleft") || keys.has("shiftright")) {
            speed *= 2.5; // High-speed sprint
          }
          if (keys.has("alt") || keys.has("altleft") || keys.has("altright")) {
            speed *= 0.3; // Fine precision crawl
          }

          const distance = speed * dt;
          moveDelta.multiplyScalar(distance);

          cam.position.add(moveDelta);
          if (controls && controls.target) {
            controls.target.add(moveDelta);
          }
          cam.updateMatrixWorld(true);
        }
      }

      if (navModeRef.current === "orbit") {
        controls.autoRotate = autoRotate;
        controls.autoRotateSpeed = 2.0;
        controls.update();
      }

      renderer.render(scene, cam);
    };

    animId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animId);
      domEl.removeEventListener("mousedown", handleCanvasMouseDown);
      window.removeEventListener("mouseup", handleCanvasMouseUp);
      domEl.removeEventListener("mousemove", handleCanvasMouseMove);
      domEl.removeEventListener("click", handleClick);
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
      controls.dispose();
      if (envTexture) {
        envTexture.dispose();
      }
      if (domEl.parentElement) {
        domEl.parentElement.removeChild(domEl);
      }
      renderer.dispose();
    };
  }, [modelUrl, canvasTheme]);

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
  const isFullscreenActive = isFullscreen || isFullscreenFallback;

  return (
    <div
      ref={outerWrapperRef}
      className={`relative select-none transition-all duration-300 ${
        isFullscreenActive
          ? "fixed inset-0 z-[9999] w-screen h-screen bg-zinc-950"
          : `w-full h-[540px] sm:h-[620px] rounded-3xl overflow-hidden border shadow-2xl ${
              isDarkCanvas
                ? "bg-[#090d16] border-zinc-800"
                : canvasTheme === "light-grey"
                ? "bg-[#f1f5f9] border-slate-300"
                : "bg-white border-slate-200"
            }`
      }`}
    >
      <div
        ref={mountRef}
        className={`w-full h-full ${
          navMode === "walk"
            ? isPointerLocked
              ? "cursor-crosshair"
              : "cursor-default"
            : "cursor-grab active:cursor-grabbing"
        }`}
      />

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
      <div className="absolute top-4 left-4 flex flex-col sm:flex-row items-start sm:items-center gap-2 z-10 pointer-events-auto">
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

      {/* TOP-RIGHT CONTROLS: Walk / Orbit Toggle, Frame 0 Spawn, Fullscreen */}
      <div className="absolute top-4 right-4 z-10 flex items-center space-x-2 pointer-events-auto">
        {/* Navigation Mode: Orbit vs Walk */}
        <button
          onClick={toggleNavMode}
          className={`flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-bold transition-all shadow-lg backdrop-blur-md border ${
            navMode === "walk"
              ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-emerald-500/20"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title={navMode === "walk" ? "Switch to Orbit Mode" : "Switch to First-Person Walk Mode (WASD)"}
        >
          {navMode === "walk" ? (
            <>
              <Footprints className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
              <span>Walk (WASD)</span>
            </>
          ) : (
            <>
              <Compass className="w-3.5 h-3.5 text-cyan-400" />
              <span>Orbit View</span>
            </>
          )}
        </button>

        {/* Start Frame (F1) preset button */}
        <button
          onClick={spawnAtFirstFrame}
          className="flex items-center space-x-1 px-2.5 py-2 rounded-xl text-xs font-bold bg-zinc-900/80 border border-zinc-800 text-cyan-300 hover:text-cyan-200 hover:bg-zinc-800/80 transition-all shadow-lg backdrop-blur-md"
          title="Teleport to Frame 1 camera viewpoint (Key F1)"
        >
          <span>Start Frame (F1)</span>
        </button>

        {/* Fullscreen Toggle */}
        <button
          onClick={toggleFullscreen}
          className={`p-2 rounded-xl text-xs font-bold transition-all shadow-lg backdrop-blur-md border ${
            isFullscreenActive
              ? "bg-indigo-500/30 text-indigo-200 border-indigo-500/60 ring-1 ring-indigo-500/50"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title={isFullscreenActive ? "Exit Fullscreen (Key F)" : "Fullscreen 3D World (Key F)"}
        >
          {isFullscreenActive ? (
            <Minimize2 className="w-4 h-4 text-indigo-300" />
          ) : (
            <Maximize2 className="w-4 h-4 text-zinc-300" />
          )}
        </button>
      </div>

      {/* BOTTOM-LEFT INTERACTIVE WASD + ELEVATION KEYPAD HUD */}
      {!measureMode && (
        <div className="absolute bottom-4 left-4 z-10 flex flex-col items-start space-y-2 pointer-events-auto">
          <div className="bg-zinc-950/85 backdrop-blur-md border border-zinc-800/90 rounded-2xl p-2 shadow-2xl flex items-center space-x-2">
            {/* WASD cluster */}
            <div className="flex flex-col items-center space-y-1">
              <button
                onMouseDown={() => {
                  pressedKeysRef.current.add("w");
                  setActiveHudKeys((prev) => ({ ...prev, w: true }));
                }}
                onMouseUp={() => {
                  pressedKeysRef.current.delete("w");
                  setActiveHudKeys((prev) => ({ ...prev, w: false }));
                }}
                onTouchStart={() => {
                  pressedKeysRef.current.add("w");
                  setActiveHudKeys((prev) => ({ ...prev, w: true }));
                }}
                onTouchEnd={() => {
                  pressedKeysRef.current.delete("w");
                  setActiveHudKeys((prev) => ({ ...prev, w: false }));
                }}
                className={`w-7 h-7 rounded-lg text-[10px] font-bold font-mono flex items-center justify-center transition-all ${
                  activeHudKeys["w"]
                    ? "bg-cyan-500 text-zinc-950 scale-95 shadow-md shadow-cyan-500/50"
                    : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                }`}
                title="Move Forward (W or Up Arrow)"
              >
                W
              </button>
              <div className="flex space-x-1">
                <button
                  onMouseDown={() => {
                    pressedKeysRef.current.add("a");
                    setActiveHudKeys((prev) => ({ ...prev, a: true }));
                  }}
                  onMouseUp={() => {
                    pressedKeysRef.current.delete("a");
                    setActiveHudKeys((prev) => ({ ...prev, a: false }));
                  }}
                  onTouchStart={() => {
                    pressedKeysRef.current.add("a");
                    setActiveHudKeys((prev) => ({ ...prev, a: true }));
                  }}
                  onTouchEnd={() => {
                    pressedKeysRef.current.delete("a");
                    setActiveHudKeys((prev) => ({ ...prev, a: false }));
                  }}
                  className={`w-7 h-7 rounded-lg text-[10px] font-bold font-mono flex items-center justify-center transition-all ${
                    activeHudKeys["a"]
                      ? "bg-cyan-500 text-zinc-950 scale-95 shadow-md shadow-cyan-500/50"
                      : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                  }`}
                  title="Move Left (A or Left Arrow)"
                >
                  A
                </button>
                <button
                  onMouseDown={() => {
                    pressedKeysRef.current.add("s");
                    setActiveHudKeys((prev) => ({ ...prev, s: true }));
                  }}
                  onMouseUp={() => {
                    pressedKeysRef.current.delete("s");
                    setActiveHudKeys((prev) => ({ ...prev, s: false }));
                  }}
                  onTouchStart={() => {
                    pressedKeysRef.current.add("s");
                    setActiveHudKeys((prev) => ({ ...prev, s: true }));
                  }}
                  onTouchEnd={() => {
                    pressedKeysRef.current.delete("s");
                    setActiveHudKeys((prev) => ({ ...prev, s: false }));
                  }}
                  className={`w-7 h-7 rounded-lg text-[10px] font-bold font-mono flex items-center justify-center transition-all ${
                    activeHudKeys["s"]
                      ? "bg-cyan-500 text-zinc-950 scale-95 shadow-md shadow-cyan-500/50"
                      : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                  }`}
                  title="Move Backward (S or Down Arrow)"
                >
                  S
                </button>
                <button
                  onMouseDown={() => {
                    pressedKeysRef.current.add("d");
                    setActiveHudKeys((prev) => ({ ...prev, d: true }));
                  }}
                  onMouseUp={() => {
                    pressedKeysRef.current.delete("d");
                    setActiveHudKeys((prev) => ({ ...prev, d: false }));
                  }}
                  onTouchStart={() => {
                    pressedKeysRef.current.add("d");
                    setActiveHudKeys((prev) => ({ ...prev, d: true }));
                  }}
                  onTouchEnd={() => {
                    pressedKeysRef.current.delete("d");
                    setActiveHudKeys((prev) => ({ ...prev, d: false }));
                  }}
                  className={`w-7 h-7 rounded-lg text-[10px] font-bold font-mono flex items-center justify-center transition-all ${
                    activeHudKeys["d"]
                      ? "bg-cyan-500 text-zinc-950 scale-95 shadow-md shadow-cyan-500/50"
                      : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                  }`}
                  title="Move Right (D or Right Arrow)"
                >
                  D
                </button>
              </div>
            </div>

            {/* Vertical elevation cluster: Space / C */}
            <div className="flex flex-col items-center space-y-1 pl-1 border-l border-zinc-800">
              <button
                onMouseDown={() => {
                  pressedKeysRef.current.add(" ");
                  setActiveHudKeys((prev) => ({ ...prev, " ": true }));
                }}
                onMouseUp={() => {
                  pressedKeysRef.current.delete(" ");
                  setActiveHudKeys((prev) => ({ ...prev, " ": false }));
                }}
                onTouchStart={() => {
                  pressedKeysRef.current.add(" ");
                  setActiveHudKeys((prev) => ({ ...prev, " ": true }));
                }}
                onTouchEnd={() => {
                  pressedKeysRef.current.delete(" ");
                  setActiveHudKeys((prev) => ({ ...prev, " ": false }));
                }}
                className={`w-7 h-7 rounded-lg text-[9px] font-bold font-mono flex items-center justify-center transition-all ${
                  activeHudKeys[" "]
                    ? "bg-emerald-400 text-zinc-950 scale-95 shadow-md shadow-emerald-400/50"
                    : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                }`}
                title="Elevate +Y (Space or E)"
              >
                +Y
              </button>
              <button
                onMouseDown={() => {
                  pressedKeysRef.current.add("c");
                  setActiveHudKeys((prev) => ({ ...prev, c: true }));
                }}
                onMouseUp={() => {
                  pressedKeysRef.current.delete("c");
                  setActiveHudKeys((prev) => ({ ...prev, c: false }));
                }}
                onTouchStart={() => {
                  pressedKeysRef.current.add("c");
                  setActiveHudKeys((prev) => ({ ...prev, c: true }));
                }}
                onTouchEnd={() => {
                  pressedKeysRef.current.delete("c");
                  setActiveHudKeys((prev) => ({ ...prev, c: false }));
                }}
                className={`w-7 h-7 rounded-lg text-[9px] font-bold font-mono flex items-center justify-center transition-all ${
                  activeHudKeys["c"]
                    ? "bg-emerald-400 text-zinc-950 scale-95 shadow-md shadow-emerald-400/50"
                    : "bg-zinc-800/80 text-zinc-300 hover:bg-zinc-700"
                }`}
                title="Descend -Y (C or Q)"
              >
                -Y
              </button>
            </div>
          </div>

          {/* Speed slider in Walk mode */}
          {navMode === "walk" && (
            <div className="flex items-center space-x-2 bg-zinc-950/85 backdrop-blur-md border border-zinc-800/90 rounded-2xl px-3 py-1.5 shadow-xl text-[11px] font-mono">
              <Sliders className="w-3 h-3 text-cyan-400" />
              <span className="text-zinc-400">Speed:</span>
              <input
                type="range"
                min="0.4"
                max="3.0"
                step="0.1"
                value={speedMultiplier}
                onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))}
                className="w-16 h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-cyan-400"
              />
              <span className="text-cyan-300 font-bold">{speedMultiplier.toFixed(1)}x</span>
            </div>
          )}
        </div>
      )}

      {/* BOTTOM-CENTER FLOATING DOCK */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center space-x-1 bg-zinc-950/85 backdrop-blur-md p-1.5 rounded-2xl border border-zinc-800 text-xs shadow-2xl z-10 pointer-events-auto">
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

        {/* Canvas Background Theme */}
        <button
          onClick={cycleCanvasTheme}
          className="px-2.5 py-1.5 rounded-xl flex items-center space-x-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
          title={`Canvas Theme: ${canvasTheme} (Click to cycle Dark-Slate / White / Light-Grey)`}
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

      {/* Floating Instructions Banner (when measure mode is active) */}
      {measureMode && (
        <div className="absolute top-4 right-4 z-10 pointer-events-auto">
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
