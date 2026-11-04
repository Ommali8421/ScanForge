import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as THREE from "three";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import {
  Download,
  RotateCw,
  AlertTriangle,
  Sliders,
  Footprints,
  Palette,
  Home,
  Layers,
  Compass,
  Zap,
  Sparkles,
} from "lucide-react";

export type SplatTheme = "dark-slate" | "deep-void" | "studio-grey" | "white";

interface CropBox {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  minZ: number;
  maxZ: number;
}

interface AlignedCamera {
  index: number;
  name: string;
  position: [number, number, number];
  up: [number, number, number];
  forward: [number, number, number];
}

interface Props {
  splatUrl: string; // Fast URL (.splat) or fallback URL
  hdUrl?: string;   // HD URL (.ply with Spherical Harmonics)
  jobId?: string;
  splatCount?: number;
  bounds?: {
    min_x: number;
    max_x: number;
    min_y: number;
    max_y: number;
    min_z: number;
    max_z: number;
  };
  dimensions?: {
    length: number;
    width: number;
    height: number;
  };
  onDownload?: (format: string) => void;
  availableFormats?: string[];
}

export const SplatViewer: React.FC<Props> = ({
  splatUrl,
  hdUrl,
  jobId,
  splatCount,
  bounds,
  dimensions: _dimensions,
  onDownload,
  availableFormats = ["splat", "ply", "zip"],
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);

  // Core Viewer States
  const [loading, setLoading] = useState(true);
  const [loadProgress, setLoadProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState("Connecting to 3DGS WebGL Stream...");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [theme, setTheme] = useState<SplatTheme>("dark-slate");
  const [splatScale, setSplatScale] = useState(1.0);
  const [showCropPanel, setShowCropPanel] = useState(false);
  const [activePreset, setActivePreset] = useState<"inside" | "dollhouse" | "topdown" | "custom">("inside");
  const [alignedCameras, setAlignedCameras] = useState<AlignedCamera[]>([]);

  // Quality Toggle: "fast" (.splat, shDegree 0) vs "hd" (.ply, shDegree 2)
  const [splatQuality, setSplatQuality] = useState<"fast" | "hd">("fast");

  // Navigation Mode: Orbit vs First-Person Walk
  const [navMode, setNavMode] = useState<"orbit" | "walk">("orbit");
  const [isPointerLocked, setIsPointerLocked] = useState(false);
  const [speedMultiplier, setSpeedMultiplier] = useState(1.0);

  // Refs for low-latency 60-144 FPS animation loop
  const pressedKeysRef = useRef<Set<string>>(new Set());
  const navModeRef = useRef<"orbit" | "walk">("orbit");
  const speedMultiplierRef = useRef(1.0);
  const horizontalRoomSpanRef = useRef(10.0);
  const yawRef = useRef(0);
  const pitchRef = useRef(0);
  const isMouseDownRef = useRef(false);
  const lastMousePosRef = useRef({ x: 0, y: 0 });
  const splatScaleRef = useRef(1.0);
  const savedPoseRef = useRef<{
    pos: THREE.Vector3;
    quat: THREE.Quaternion;
    target?: THREE.Vector3;
  } | null>(null);

  // 6-slider crop box state & ref
  const [cropBox, setCropBox] = useState<CropBox>({
    minX: -15,
    maxX: 15,
    minY: -0.5,
    maxY: 8,
    minZ: -15,
    maxZ: 15,
  });
  const cropBoxRef = useRef<CropBox>(cropBox);

  // Keep synchronous refs updated
  useEffect(() => {
    navModeRef.current = navMode;
  }, [navMode]);

  useEffect(() => {
    speedMultiplierRef.current = speedMultiplier;
  }, [speedMultiplier]);

  useEffect(() => {
    cropBoxRef.current = cropBox;
  }, [cropBox]);

  useEffect(() => {
    splatScaleRef.current = splatScale;
  }, [splatScale]);

  const horizontalRoomSpan = useMemo(() => {
    if (bounds) {
      return Math.max(bounds.max_x - bounds.min_x, bounds.max_z - bounds.min_z, 2.0);
    }
    return 10.0;
  }, [bounds]);

  useEffect(() => {
    horizontalRoomSpanRef.current = horizontalRoomSpan;
  }, [horizontalRoomSpan]);

  // Compute active streaming URL and format based on quality mode
  const activeUrl = useMemo(() => {
    if (splatQuality === "hd") {
      if (hdUrl) return hdUrl;
      if (jobId) return `/api/jobs/${jobId}/artifacts/model.ply`;
      return splatUrl.replace(/\.splat(\?.*)?$/i, ".ply$1");
    } else {
      if (splatUrl) {
        if (splatUrl.toLowerCase().endsWith(".ply")) {
          return splatUrl.replace(/\.ply(\?.*)?$/i, ".splat$1");
        }
        return splatUrl;
      }
      if (jobId) return `/api/jobs/${jobId}/artifacts/model.splat`;
      return "";
    }
  }, [splatQuality, splatUrl, hdUrl, jobId]);

  const isPly = activeUrl.toLowerCase().includes(".ply") || splatQuality === "hd";
  const targetFormat = isPly ? GaussianSplats3D.SceneFormat.Ply : GaussianSplats3D.SceneFormat.Splat;
  const shDegree = splatQuality === "hd" ? 2 : 0;

  const getThemeBg = (t: SplatTheme) => {
    switch (t) {
      case "deep-void":
        return "#000000";
      case "studio-grey":
        return "#1e293b";
      case "white":
        return "#ffffff";
      case "dark-slate":
      default:
        return "#090d16";
    }
  };

  const cycleTheme = () => {
    setTheme((prev) => {
      if (prev === "dark-slate") return "studio-grey";
      if (prev === "studio-grey") return "deep-void";
      if (prev === "deep-void") return "white";
      return "dark-slate";
    });
  };

  // Fetch aligned camera poses if available
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    fetch(`/api/jobs/${jobId}/artifacts/cameras_aligned.json`)
      .then((res) => {
        if (!res.ok) return null;
        return res.json();
      })
      .then((data) => {
        if (active && data?.cameras && Array.isArray(data.cameras)) {
          setAlignedCameras(data.cameras);
        }
      })
      .catch((e) => {
        console.debug("cameras_aligned.json not available:", e);
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  // Hook GPU shader clipping onto splat mesh material
  const applyGpuClipping = useCallback((box: CropBox) => {
    if (!viewerRef.current?.splatMesh) return;
    const mesh = viewerRef.current.splatMesh;
    const mat = mesh.material;
    if (!mat) return;

    if (!mat.uniforms.sfCropMin) {
      mat.uniforms.sfCropMin = { value: new THREE.Vector3(box.minX, box.minY, box.minZ) };
      mat.uniforms.sfCropMax = { value: new THREE.Vector3(box.maxX, box.maxY, box.maxZ) };
      mat.uniforms.sfCropEnabled = { value: 1 };

      if (!mat.vertexShader.includes("sfCropMin")) {
        mat.vertexShader =
          `
          uniform vec3 sfCropMin;
          uniform vec3 sfCropMax;
          uniform int sfCropEnabled;
        ` + mat.vertexShader;

        mat.vertexShader = mat.vertexShader.replace(
          "vec3 splatCenter = uintBitsToFloat(uvec3(sampledCenterColor.gba));",
          `vec3 splatCenter = uintBitsToFloat(uvec3(sampledCenterColor.gba));
          if (sfCropEnabled == 1) {
            if (splatCenter.x < sfCropMin.x || splatCenter.x > sfCropMax.x ||
                splatCenter.y < sfCropMin.y || splatCenter.y > sfCropMax.y ||
                splatCenter.z < sfCropMin.z || splatCenter.z > sfCropMax.z) {
              gl_Position = vec4(0.0, 0.0, 2.0, 1.0);
              return;
            }
          }`
        );
        mat.needsUpdate = true;
      }
    } else {
      mat.uniforms.sfCropMin.value.set(box.minX, box.minY, box.minZ);
      mat.uniforms.sfCropMax.value.set(box.maxX, box.maxY, box.maxZ);
      mat.uniforms.sfCropEnabled.value = 1;
    }
  }, []);

  // Update clipping when cropBox changes
  useEffect(() => {
    applyGpuClipping(cropBox);
  }, [cropBox, applyGpuClipping]);

  // Helper to completely neutralize OrbitControls built-in key interception
  const neutralizeOrbitControlsKeys = (viewerInstance: any) => {
    if (!viewerInstance) return;
    const seen = new Set();
    const ctrls = [
      viewerInstance.controls,
      viewerInstance.perspectiveControls,
      viewerInstance.orthographicControls,
    ];
    for (const c of ctrls) {
      if (c && !seen.has(c)) {
        seen.add(c);
        try {
          if (c._domElementKeyEvents) {
            c.stopListenToKeyEvents?.();
          }
        } catch (err) {
          console.debug("stopListenToKeyEvents notice:", err);
        }
        try {
          c.listenToKeyEvents = () => {}; // Neutralize re-binding
          c.keys = { LEFT: "", UP: "", RIGHT: "", BOTTOM: "" };
          c.handleKeyDown = () => {}; // Kill keydown handler completely
          c.enableKeys = false;
        } catch (err) {
          console.debug("OrbitControls key neutralization notice:", err);
        }
      }
    }
    if (viewerInstance.keyDownListener) {
      try {
        window.removeEventListener("keydown", viewerInstance.keyDownListener);
        viewerInstance.keyDownListener = () => {};
      } catch (_) {}
    }
  };

  // View Preset: Inside Room
  const handlePresetInside = useCallback(() => {
    setActivePreset("inside");
    if (!viewerRef.current?.camera) return;
    neutralizeOrbitControlsKeys(viewerRef.current);
    const cam = viewerRef.current.camera;
    const controls = viewerRef.current.controls;

    // Reset crop box to full room
    if (bounds) {
      const fullBox: CropBox = {
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: Math.ceil(bounds.max_y + 1.0),
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      };
      setCropBox(fullBox);
      cropBoxRef.current = fullBox;
    }

    if (alignedCameras.length > 0) {
      const cam0 = alignedCameras[0];
      const pos = cam0.position;
      const fwd = cam0.forward;
      cam.position.set(pos[0], pos[1], pos[2]);
      if (controls?.target) {
        controls.target.set(
          pos[0] + fwd[0] * 3.0,
          pos[1] + fwd[1] * 3.0,
          pos[2] + fwd[2] * 3.0
        );
      }
    } else {
      cam.position.set(0, 1.4, 0);
      if (controls?.target) {
        controls.target.set(0, 1.3, 3.0);
      }
    }

    if (navModeRef.current === "walk") {
      if (controls) controls.enabled = false;
      const euler = new THREE.Euler(0, 0, 0, "YXZ");
      euler.setFromQuaternion(cam.quaternion, "YXZ");
      yawRef.current = euler.y;
      pitchRef.current = Math.max((-85 * Math.PI) / 180, Math.min((85 * Math.PI) / 180, euler.x));
      cam.rotation.order = "YXZ";
      cam.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");
    } else {
      if (controls) {
        controls.enabled = true;
        controls.update?.();
      }
    }
  }, [alignedCameras, bounds]);

  // View Preset: Dollhouse Cutaway (Orbits elevated 3/4 with top 18% ceiling cutaway)
  const handlePresetDollhouse = useCallback(() => {
    setActivePreset("dollhouse");
    if (!viewerRef.current?.camera) return;
    neutralizeOrbitControlsKeys(viewerRef.current);
    const cam = viewerRef.current.camera;
    const controls = viewerRef.current.controls;

    let cx = 0, cy = 1.0, cz = 0;
    let spanX = 5.0, spanY = 2.8, spanZ = 5.0;

    if (bounds) {
      cx = (bounds.min_x + bounds.max_x) / 2;
      cy = (bounds.min_y + bounds.max_y) / 2;
      cz = (bounds.min_z + bounds.max_z) / 2;
      spanX = Math.max(bounds.max_x - bounds.min_x, 4.0);
      spanY = Math.max(bounds.max_y - bounds.min_y, 2.0);
      spanZ = Math.max(bounds.max_z - bounds.min_z, 4.0);

      // Cut away top 18% of ceiling
      const ceilingCutY = bounds.max_y - 0.18 * spanY;
      const cutBox: CropBox = {
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: ceilingCutY,
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      };
      setCropBox(cutBox);
      cropBoxRef.current = cutBox;
    }

    // Elevated 3/4 viewpoint looking down at room centroid
    const eyeX = cx - 1.1 * spanX;
    const eyeY = cy + 1.2 * spanY + 1.0;
    const eyeZ = cz - 1.1 * spanZ;
    cam.position.set(eyeX, eyeY, eyeZ);

    if (controls?.target) {
      controls.target.set(cx, cy * 0.5, cz);
      controls.enabled = true;
      controls.update?.();
    }
    setNavMode("orbit");
    navModeRef.current = "orbit";
  }, [bounds]);

  // View Preset: Floor Plan Top-Down
  const handlePresetTopDown = useCallback(() => {
    setActivePreset("topdown");
    if (!viewerRef.current?.camera) return;
    neutralizeOrbitControlsKeys(viewerRef.current);
    const cam = viewerRef.current.camera;
    const controls = viewerRef.current.controls;

    let cx = 0, cz = 0;
    let span = 6.0;

    if (bounds) {
      cx = (bounds.min_x + bounds.max_x) / 2;
      cz = (bounds.min_z + bounds.max_z) / 2;
      span = Math.max(bounds.max_x - bounds.min_x, bounds.max_z - bounds.min_z, 5.0);

      const planBox: CropBox = {
        minX: Math.floor(bounds.min_x - 1.0),
        maxX: Math.ceil(bounds.max_x + 1.0),
        minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
        maxY: Math.ceil(bounds.max_y + 1.0),
        minZ: Math.floor(bounds.min_z - 1.0),
        maxZ: Math.ceil(bounds.max_z + 1.0),
      };
      setCropBox(planBox);
      cropBoxRef.current = planBox;
    }

    cam.position.set(cx, span * 1.5, cz);
    if (controls?.target) {
      controls.target.set(cx, 0.0, cz);
      controls.enabled = true;
      controls.update?.();
    }
    setNavMode("orbit");
    navModeRef.current = "orbit";
  }, [bounds]);

  // Seamless Handoff between Orbit and First-Person Walk Mode
  const toggleNavMode = useCallback(() => {
    if (!viewerRef.current?.camera) return;
    neutralizeOrbitControlsKeys(viewerRef.current);
    const cam = viewerRef.current.camera;
    const controls = viewerRef.current.controls;

    if (navMode === "orbit") {
      // Orbit -> Walk:
      // 1. Disable OrbitControls so they don't overwrite camera transforms
      if (controls) {
        controls.enabled = false;
      }
      // 2. Extract yaw and pitch directly from camera quaternion with 0 jump
      const euler = new THREE.Euler(0, 0, 0, "YXZ");
      euler.setFromQuaternion(cam.quaternion, "YXZ");
      yawRef.current = euler.y;
      pitchRef.current = Math.max((-85 * Math.PI) / 180, Math.min((85 * Math.PI) / 180, euler.x));
      cam.rotation.order = "YXZ";
      cam.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");

      setNavMode("walk");
      navModeRef.current = "walk";
    } else {
      // Walk -> Orbit:
      // 1. Release pointer lock if active
      if (document.pointerLockElement) {
        document.exitPointerLock?.();
      }
      // 2. Set target in front of camera at room-adaptive distance
      const viewDir = new THREE.Vector3();
      cam.getWorldDirection(viewDir);
      if (controls?.target) {
        const targetDist = Math.max(1.0, 0.25 * horizontalRoomSpanRef.current);
        controls.target.copy(cam.position).addScaledVector(viewDir, targetDist);
        controls.enabled = true;
        controls.update?.();
      }

      setNavMode("orbit");
      navModeRef.current = "orbit";
    }
  }, [navMode]);

  // Keyboard Event Listeners (Set<string> tracking with blur protection & event capturing)
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
        // Prevent default browser behavior (e.g. Space/Arrow scrolling)
        e.preventDefault();
        // Stop OrbitControls on window from receiving the key and rotating or panning
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

  // Continuous Camera-Relative 3D Movement Loop:
  // W: forward, S: backward, A: left, D: right, Space: up, Ctrl: down, Shift: speed boost
  useEffect(() => {
    let animId: number;
    let lastTime = performance.now();

    const loop = (now: number) => {
      animId = requestAnimationFrame(loop);
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      if (!viewerRef.current?.camera) return;
      const cam = viewerRef.current.camera;
      const keys = pressedKeysRef.current;
      if (keys.size === 0) return;

      // Extract current camera view direction
      const viewDir = new THREE.Vector3();
      cam.getWorldDirection(viewDir);

      // Horizontal forward vector on XZ plane
      let forward = new THREE.Vector3(viewDir.x, 0, viewDir.z);
      if (forward.lengthSq() < 1e-4) {
        forward.set(cam.up.x, 0, cam.up.z);
      }
      if (forward.lengthSq() < 1e-4) {
        forward.set(0, 0, -1);
      } else {
        forward.normalize();
      }

      // Horizontal right strafe vector = forward x (0, 1, 0)
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

        // Speed modifiers: Shift = 2.5x speed boost, Alt = 0.3x
        let speedModifier = speedMultiplierRef.current || 1.0;
        if (keys.has("shift") || keys.has("shiftleft") || keys.has("shiftright")) {
          speedModifier *= 2.5;
        }
        if (keys.has("alt") || keys.has("altleft") || keys.has("altright")) {
          speedModifier *= 0.3;
        }

        const baseSpeed = Math.max(1.0, 0.25 * horizontalRoomSpanRef.current);
        const distance = baseSpeed * speedModifier * dt;
        moveDelta.multiplyScalar(distance);

        cam.position.add(moveDelta);

        // Always translate controls.target by the EXACT same moveDelta so OrbitControls never rotates or fights camera!
        const controls = viewerRef.current?.controls;
        if (controls && controls.target) {
          controls.target.add(moveDelta);
          controls.update?.();
        }
      }
    };

    animId = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(animId);
    };
  }, []);

  // Canvas Click Handler: Engage Pointer Lock when in Walk Mode
  const handleCanvasClick = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button, input, select, textarea")) return;
    if (navModeRef.current === "walk") {
      const dom = containerRef.current;
      if (dom && document.pointerLockElement !== dom) {
        try {
          dom.requestPointerLock?.();
        } catch (err) {
          console.debug("Pointer lock request error:", err);
        }
      }
    }
  }, []);

  // Pointer Lock Change Listener
  useEffect(() => {
    const onPointerLockChange = () => {
      const isLocked = document.pointerLockElement === containerRef.current;
      setIsPointerLocked(isLocked);
    };
    document.addEventListener("pointerlockchange", onPointerLockChange);
    return () => {
      document.removeEventListener("pointerlockchange", onPointerLockChange);
    };
  }, []);

  // Mouse Look (Pointer Lock or Left-Click Drag Fallback)
  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (navModeRef.current !== "walk") return;
      if ((e.target as HTMLElement)?.closest?.("button, input, select, textarea")) return;
      if (e.button === 0) {
        isMouseDownRef.current = true;
        lastMousePosRef.current = { x: e.clientX, y: e.clientY };
      }
    };

    const onMouseUp = () => {
      isMouseDownRef.current = false;
    };

    const onMouseMove = (e: MouseEvent) => {
      if (navModeRef.current !== "walk" || !viewerRef.current?.camera) return;
      const isLocked = document.pointerLockElement === containerRef.current;
      if (!isLocked && !isMouseDownRef.current) return;

      let dx = 0;
      let dy = 0;
      if (isLocked) {
        dx = e.movementX;
        dy = e.movementY;
      } else {
        dx = e.clientX - lastMousePosRef.current.x;
        dy = e.clientY - lastMousePosRef.current.y;
        lastMousePosRef.current = { x: e.clientX, y: e.clientY };
      }

      // Filter out large spikes on pointer lock engagement
      if (Math.abs(dx) > 250 || Math.abs(dy) > 250) return;

      const lookSpeed = 0.0022;
      yawRef.current -= dx * lookSpeed;
      const maxPitch = (85 * Math.PI) / 180;
      pitchRef.current = Math.max(-maxPitch, Math.min(maxPitch, pitchRef.current - dy * lookSpeed));

      const cam = viewerRef.current.camera;
      cam.rotation.order = "YXZ";
      cam.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");
    };

    const dom = containerRef.current;
    if (dom) {
      dom.addEventListener("mousedown", onMouseDown);
    }
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      if (dom) {
        dom.removeEventListener("mousedown", onMouseDown);
      }
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // Initialize and Re-Initialize GaussianSplats3D.Viewer
  useEffect(() => {
    if (!containerRef.current || !activeUrl) return;

    setLoading(true);
    setLoadProgress(0);
    setLoadingStage(
      splatQuality === "hd"
        ? "Streaming HD PLY with Spherical Harmonics Degree 2..."
        : "Connecting to Fast 3DGS WebGL Stream..."
    );
    setLoadError(null);

    let disposed = false;
    let viewer: any = null;

    // Preserve previous camera pose across quality switches
    const prevCam = viewerRef.current?.camera;
    const prevControls = viewerRef.current?.controls;
    if (prevCam) {
      savedPoseRef.current = {
        pos: prevCam.position.clone(),
        quat: prevCam.quaternion.clone(),
        target: prevControls?.target ? prevControls.target.clone() : undefined,
      };
    }

    // Dispose old viewer
    if (viewerRef.current) {
      try {
        viewerRef.current.dispose();
      } catch (e) {
        console.debug("Previous viewer dispose exception:", e);
      }
      viewerRef.current = null;
    }

    try {
      const initialPos: [number, number, number] = savedPoseRef.current
        ? [savedPoseRef.current.pos.x, savedPoseRef.current.pos.y, savedPoseRef.current.pos.z]
        : [0, 1.4, 0];
      const initialLookAt: [number, number, number] = savedPoseRef.current?.target
        ? [savedPoseRef.current.target.x, savedPoseRef.current.target.y, savedPoseRef.current.target.z]
        : [0, 1.3, 3.0];

      viewer = new GaussianSplats3D.Viewer({
        rootElement: containerRef.current,
        cameraUp: [0, 1, 0],
        initialCameraPosition: initialPos,
        initialCameraLookAt: initialLookAt,
        sharedMemoryForWorkers: false,
        gpuAcceleratedSort: false,
        antialiased: true,
        sphericalHarmonicsDegree: shDegree,
        selfDrivenMode: true,
        useBuiltInControls: true,
      });

      viewerRef.current = viewer;
      neutralizeOrbitControlsKeys(viewer);

      viewer
        .addSplatScene(activeUrl, {
          format: targetFormat,
          splatAlphaRemovalThreshold: 5,
          showLoadingUI: false,
          position: [0, 0, 0],
          rotation: [0, 0, 0, 1],
          scale: [1, 1, 1],
          onProgress: (percent: number) => {
            if (!disposed) {
              const p = Math.min(Math.round(percent), 100);
              setLoadProgress(p);
              if (p >= 100) {
                setLoadingStage("Rasterizing 3D Gaussian Splats...");
              } else {
                setLoadingStage(
                  splatQuality === "hd"
                    ? `Downloading HD Splats (.ply SH degree 2)... ${p}%`
                    : `Downloading Fast Splat Payload (.splat)... ${p}%`
                );
              }
            }
          },
        })
        .then(() => {
          if (disposed) return;

          try {
            viewer.start();
            neutralizeOrbitControlsKeys(viewer);
          } catch (e) {
            console.debug("viewer.start exception:", e);
          }

          // Re-apply GPU clipping uniforms
          applyGpuClipping(cropBoxRef.current);

          // Restore splat scale
          if (viewer.splatMesh) {
            try {
              viewer.splatMesh.splatScale = splatScaleRef.current;
            } catch (e) {
              console.debug("splatScale restore exception:", e);
            }
          }

          // Restore saved camera pose or perform initial auto-framing
          if (savedPoseRef.current && viewer.camera) {
            viewer.camera.position.copy(savedPoseRef.current.pos);
            viewer.camera.quaternion.copy(savedPoseRef.current.quat);
            if (viewer.controls?.target && savedPoseRef.current.target) {
              viewer.controls.target.copy(savedPoseRef.current.target);
            }
            if (navModeRef.current === "walk") {
              if (viewer.controls) viewer.controls.enabled = false;
              const euler = new THREE.Euler(0, 0, 0, "YXZ");
              euler.setFromQuaternion(viewer.camera.quaternion, "YXZ");
              yawRef.current = euler.y;
              pitchRef.current = Math.max((-85 * Math.PI) / 180, Math.min((85 * Math.PI) / 180, euler.x));
              viewer.camera.rotation.order = "YXZ";
              viewer.camera.rotation.set(pitchRef.current, yawRef.current, 0, "YXZ");
            } else {
              if (viewer.controls) {
                viewer.controls.enabled = true;
                viewer.controls.update?.();
              }
            }
          } else {
            // First time auto-framing
            try {
              let cx = 0, cy = 1.0, cz = 0;
              let span = 5.0;

              if (bounds) {
                cx = (bounds.min_x + bounds.max_x) / 2;
                cy = (bounds.min_y + bounds.max_y) / 2;
                cz = (bounds.min_z + bounds.max_z) / 2;
                span = Math.max(bounds.max_x - bounds.min_x, bounds.max_z - bounds.min_z, 4.0);

                const pad = Math.max(span * 0.2, 1.5);
                const initialBox: CropBox = {
                  minX: Math.floor(bounds.min_x - pad),
                  maxX: Math.ceil(bounds.max_x + pad),
                  minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
                  maxY: Math.ceil(bounds.max_y + pad),
                  minZ: Math.floor(bounds.min_z - pad),
                  maxZ: Math.ceil(bounds.max_z + pad),
                };
                setCropBox(initialBox);
                cropBoxRef.current = initialBox;
                applyGpuClipping(initialBox);
              }

              if (viewer.camera) {
                viewer.camera.near = 0.05;
                viewer.camera.far = 2000.0;
                viewer.camera.updateProjectionMatrix();

                // Spawn at interior eye-level looking forward
                viewer.camera.position.set(cx, Math.max(cy * 0.6, 1.3), cz - span * 0.1);
                if (viewer.controls?.target) {
                  viewer.controls.target.set(cx, Math.max(cy * 0.6, 1.3), cz + span * 0.6);
                  viewer.controls.update?.();
                }
              }
            } catch (e) {
              console.debug("Camera auto-framing exception:", e);
            }
          }

          setLoading(false);
        })
        .catch((err: any) => {
          if (!disposed) {
            console.error("GaussianSplats3D viewer scene load error:", err);
            setLoadError(`Failed to render 3D Gaussian Splat: ${err?.message || err}`);
            setLoading(false);
          }
        });
    } catch (err: any) {
      console.error("GaussianSplats3D initialization error:", err);
      setLoadError(`Failed to initialize 3DGS WebGL Viewer: ${err?.message || err}`);
      setLoading(false);
    }

    return () => {
      disposed = true;
      if (viewer) {
        try {
          viewer.dispose();
        } catch (e) {
          console.debug("Viewer dispose exception:", e);
        }
      }
      viewerRef.current = null;
    };
  }, [activeUrl, splatQuality, targetFormat, shDegree, bounds, applyGpuClipping]);

  const handleSplatScaleChange = (val: number) => {
    setSplatScale(val);
    splatScaleRef.current = val;
    if (viewerRef.current?.splatMesh) {
      try {
        viewerRef.current.splatMesh.splatScale = val;
      } catch (e) {
        console.debug("splatScale update:", e);
      }
    }
  };

  return (
    <div
      className="relative w-full h-[560px] lg:h-[650px] rounded-3xl overflow-hidden border border-zinc-800/80 shadow-2xl transition-colors duration-300"
      style={{ backgroundColor: getThemeBg(theme) }}
    >
      {/* 3DGS Canvas Container */}
      <div
        ref={containerRef}
        onClick={handleCanvasClick}
        className={`absolute inset-0 w-full h-full ${
          navMode === "walk"
            ? isPointerLocked
              ? "cursor-crosshair"
              : "cursor-pointer"
            : "cursor-grab active:cursor-grabbing"
        }`}
      />

      {/* Loading Overlay */}
      {loading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950/80 backdrop-blur-md z-30 transition-opacity">
          <div className="w-12 h-12 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mb-4" />
          <p className="text-sm font-mono text-zinc-200 tracking-wider font-semibold">
            {loadingStage}
          </p>
          <div className="w-48 h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-3">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-300"
              style={{ width: `${Math.max(loadProgress, 5)}%` }}
            />
          </div>
          <span className="text-xs font-mono text-zinc-500 mt-2">
            World-centered (0, 0, 0) • Floor flush at Y=0.000m • +Y Up
          </span>
        </div>
      )}

      {/* Error Card */}
      {loadError && (
        <div className="absolute inset-x-6 top-6 z-40 max-w-lg mx-auto p-4 rounded-2xl bg-rose-950/80 border border-rose-800 text-rose-200 text-xs backdrop-blur-md flex items-start space-x-3 shadow-2xl">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 text-rose-400 mt-0.5" />
          <div>
            <h4 className="font-bold text-rose-300">Splat Rendering Error</h4>
            <p className="mt-1 text-rose-300/80 font-mono leading-relaxed">{loadError}</p>
          </div>
        </div>
      )}

      {/* Top Left Status & HUD Badge */}
      <div className="absolute top-5 left-5 z-20 flex flex-col space-y-2 pointer-events-none">
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-zinc-900/80 border border-zinc-700/80 backdrop-blur-md shadow-lg pointer-events-auto">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-bold text-zinc-200 tracking-tight">3DGS Splat Studio</span>
          <span className="text-zinc-500 text-xs">•</span>
          <span className="text-xs font-mono text-cyan-400">
            {splatCount ? `${splatCount.toLocaleString()} splats` : "Native 32-byte stream"}
          </span>
        </div>
        <div className="text-[11px] font-mono text-zinc-400/90 px-3 py-1 rounded-lg bg-zinc-950/60 backdrop-blur-sm border border-zinc-800/60 w-fit">
          Up: +Y (0, 1, 0) • Floor flush at Y=0.000m • Center (0, 0)
        </div>
      </div>

      {/* Top Center 1-Click View Presets */}
      <div className="absolute top-5 inset-x-0 z-20 flex justify-center pointer-events-none">
        <div className="flex items-center space-x-1 p-1 rounded-2xl bg-zinc-950/80 border border-zinc-800/90 backdrop-blur-xl shadow-2xl pointer-events-auto">
          <button
            onClick={handlePresetInside}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "inside"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Inside Room Walkthrough Camera"
          >
            <Home className="w-3.5 h-3.5" />
            <span>Inside Room</span>
          </button>

          <button
            onClick={handlePresetDollhouse}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "dollhouse"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Dollhouse 3/4 Overview with Ceiling Cutaway"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Dollhouse Cutaway</span>
          </button>

          <button
            onClick={handlePresetTopDown}
            className={`flex items-center space-x-1.5 px-3 py-1 rounded-xl text-xs font-bold transition-all ${
              activePreset === "topdown"
                ? "bg-cyan-500 text-zinc-950 shadow-md shadow-cyan-500/20"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/60"
            }`}
            title="Floor Plan Top-Down View"
          >
            <Compass className="w-3.5 h-3.5" />
            <span>Floor Plan</span>
          </button>
        </div>
      </div>

      {/* Top Right Actions Toolbar */}
      <div className="absolute top-5 right-5 z-20 flex items-center space-x-2">
        {/* Fast (.splat) vs HD Reflections (.ply SH) Mode Toggle */}
        <div className="flex items-center p-0.5 rounded-xl bg-zinc-900/80 border border-zinc-800 backdrop-blur-md shadow-lg">
          <button
            onClick={() => setSplatQuality("fast")}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
              splatQuality === "fast"
                ? "bg-amber-500/25 text-amber-300 border border-amber-500/50 shadow-sm"
                : "text-zinc-400 hover:text-white"
            }`}
            title="Fast 32-byte .splat stream (Instant loading, Degree 0 SH)"
          >
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Fast (.splat)</span>
          </button>
          <button
            onClick={() => setSplatQuality("hd")}
            className={`flex items-center space-x-1.5 px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
              splatQuality === "hd"
                ? "bg-indigo-500/30 text-indigo-200 border border-indigo-500/50 shadow-sm shadow-indigo-500/20"
                : "text-zinc-400 hover:text-white"
            }`}
            title="HD Reflections .ply with Spherical Harmonics Degree 2"
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>HD Reflections (.ply SH)</span>
          </button>
        </div>

        {/* Orbit vs Walk Mode Toggle */}
        <button
          onClick={toggleNavMode}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-lg backdrop-blur-md border ${
            navMode === "walk"
              ? "bg-cyan-500/25 text-cyan-200 border-cyan-500/60 shadow-cyan-500/20 ring-1 ring-cyan-500/40"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title="WASD: Move Forward/Back/Left/Right • Space: Up • Ctrl: Down • Shift: Speed Up"
        >
          <Footprints className="w-3.5 h-3.5 text-cyan-400" />
          <span>{navMode === "walk" ? "Walk Mode (WASD)" : "Orbit"}</span>
        </button>

        {/* Speed Slider in HUD */}
        <div
          className="hidden sm:flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-zinc-900/80 border border-zinc-800 text-xs backdrop-blur-md shadow-lg"
          title="Nav Speed Multiplier (W/S/A/D: Move, Space: Up, Ctrl: Down, Shift: 2.5x Boost)"
        >
          <span className="text-[11px] font-mono text-zinc-400">Speed</span>
          <input
            type="range"
            min="0.2"
            max="3.0"
            step="0.1"
            value={speedMultiplier}
            onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))}
            className="w-14 accent-cyan-400 h-1 bg-zinc-800 rounded-lg cursor-pointer"
          />
          <span className="font-mono text-[10px] text-cyan-400 w-6 text-right">
            {speedMultiplier.toFixed(1)}x
          </span>
        </div>

        {/* Crop panel toggle */}
        <button
          onClick={() => setShowCropPanel(!showCropPanel)}
          className={`p-2 rounded-xl text-xs transition-all shadow-lg backdrop-blur-md border ${
            showCropPanel
              ? "bg-indigo-500/20 text-indigo-300 border-indigo-500/50"
              : "bg-zinc-900/80 text-zinc-300 border-zinc-800 hover:text-white hover:bg-zinc-800"
          }`}
          title="Bounding Crop Box & Clipping"
        >
          <Sliders className="w-4 h-4" />
        </button>

        {/* Theme cycle */}
        <button
          onClick={cycleTheme}
          className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all shadow-lg backdrop-blur-md"
          title={`Canvas theme: ${theme}`}
        >
          <Palette className="w-4 h-4" />
        </button>

        {/* Reset view */}
        <button
          onClick={handlePresetInside}
          className="p-2 rounded-xl bg-zinc-900/80 border border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-800 transition-all shadow-lg backdrop-blur-md"
          title="Reset Camera View"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>

      {/* Walk Mode HUD Help Banner */}
      {navMode === "walk" && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center space-x-3 px-3.5 py-1.5 rounded-full bg-zinc-950/90 border border-cyan-500/40 text-zinc-200 text-xs backdrop-blur-md shadow-xl animate-fade-in pointer-events-none">
          <div className="flex items-center space-x-1 font-mono text-[11px]">
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-cyan-300 font-bold">
              W A S D
            </span>
            <span className="text-zinc-400">Move</span>
          </div>
          <span className="text-zinc-600">•</span>
          <div className="flex items-center space-x-1 font-mono text-[11px]">
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-cyan-300 font-bold">
              Q / E
            </span>
            <span className="text-zinc-400">Fly</span>
          </div>
          <span className="text-zinc-600">•</span>
          <div className="flex items-center space-x-1 font-mono text-[11px]">
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-amber-300 font-bold">
              Shift
            </span>
            <span className="text-zinc-400">2.5x</span>
            <span className="px-1.5 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-purple-300 font-bold ml-1">
              Alt
            </span>
            <span className="text-zinc-400">0.3x</span>
          </div>
          <span className="text-zinc-600">•</span>
          <span className="text-xs text-zinc-300 font-medium">
            {isPointerLocked ? "🔒 Pointer Locked (Esc to unlock)" : "🖱️ Click canvas to lock mouse look"}
          </span>
        </div>
      )}

      {/* Floating Crop Sliders Panel */}
      {showCropPanel && (
        <div className="absolute top-16 right-5 z-20 w-72 p-4 rounded-2xl bg-zinc-950/90 border border-zinc-800 backdrop-blur-xl shadow-2xl space-y-3 font-mono text-xs">
          <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
            <span className="font-bold text-zinc-200">Real-Time Crop Box</span>
            <button
              onClick={() => {
                setActivePreset("custom");
                if (bounds) {
                  const resetBox: CropBox = {
                    minX: Math.floor(bounds.min_x - 1.0),
                    maxX: Math.ceil(bounds.max_x + 1.0),
                    minY: Math.floor(Math.min(-0.2, bounds.min_y - 0.2)),
                    maxY: Math.ceil(bounds.max_y + 1.0),
                    minZ: Math.floor(bounds.min_z - 1.0),
                    maxZ: Math.ceil(bounds.max_z + 1.0),
                  };
                  setCropBox(resetBox);
                  cropBoxRef.current = resetBox;
                }
              }}
              className="text-[10px] text-zinc-400 hover:text-cyan-400 transition-colors"
            >
              Reset
            </button>
          </div>

          {/* Nav / Walk Speed */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Nav / Walk Speed</span>
              <span className="text-cyan-300">{speedMultiplier.toFixed(1)}x</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="3.0"
              step="0.1"
              value={speedMultiplier}
              onChange={(e) => setSpeedMultiplier(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 h-1 bg-zinc-800 rounded-lg cursor-pointer"
            />
          </div>

          {/* Splat Scale */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Splat Scale</span>
              <span className="text-cyan-300">{splatScale.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="2.5"
              step="0.05"
              value={splatScale}
              onChange={(e) => handleSplatScaleChange(parseFloat(e.target.value))}
              className="w-full accent-cyan-400 h-1 bg-zinc-800 rounded-lg cursor-pointer"
            />
          </div>

          {/* X Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>X Axis (Width)</span>
              <span className="text-zinc-300">{cropBox.minX}m to {cropBox.maxX}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-20"
                max="0"
                step="0.5"
                value={cropBox.minX}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, minX: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-indigo-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="20"
                step="0.5"
                value={cropBox.maxX}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, maxX: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-indigo-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>

          {/* Y Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Y Axis (Height)</span>
              <span className="text-zinc-300">{cropBox.minY}m to {cropBox.maxY}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-2"
                max="2"
                step="0.1"
                value={cropBox.minY}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, minY: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-emerald-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0.5"
                max="12"
                step="0.2"
                value={cropBox.maxY}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, maxY: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-emerald-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>

          {/* Z Range */}
          <div>
            <div className="flex justify-between text-zinc-400 mb-1 text-[11px]">
              <span>Z Axis (Depth)</span>
              <span className="text-zinc-300">{cropBox.minZ}m to {cropBox.maxZ}m</span>
            </div>
            <div className="flex space-x-2">
              <input
                type="range"
                min="-20"
                max="0"
                step="0.5"
                value={cropBox.minZ}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, minZ: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-rose-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
              <input
                type="range"
                min="0"
                max="20"
                step="0.5"
                value={cropBox.maxZ}
                onChange={(e) => {
                  setActivePreset("custom");
                  const updated = { ...cropBox, maxZ: parseFloat(e.target.value) };
                  setCropBox(updated);
                  cropBoxRef.current = updated;
                }}
                className="w-1/2 accent-rose-500 h-1 bg-zinc-800 rounded-lg cursor-pointer"
              />
            </div>
          </div>
        </div>
      )}

      {/* Bottom Center Download Strip */}
      <div className="absolute bottom-5 inset-x-0 z-20 flex justify-center pointer-events-none">
        <div className="flex items-center space-x-2 px-3 py-2 rounded-2xl bg-zinc-950/80 border border-zinc-800/90 backdrop-blur-xl shadow-2xl pointer-events-auto">
          <span className="text-xs font-bold text-zinc-400 mr-2 font-mono flex items-center space-x-1">
            <Download className="w-3.5 h-3.5 text-cyan-400" />
            <span>Downloads:</span>
          </span>
          {availableFormats.map((fmt) => (
            <button
              key={fmt}
              onClick={() => onDownload && onDownload(fmt)}
              className="px-2.5 py-1 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-cyan-500/50 hover:bg-zinc-800 text-zinc-300 hover:text-white text-xs font-mono font-bold transition-all"
            >
              .{fmt}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
