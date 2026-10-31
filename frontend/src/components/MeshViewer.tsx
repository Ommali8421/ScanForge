import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Eye, RotateCw, Crosshair, ZoomIn, ZoomOut, RefreshCw, Sun, Moon, AlertTriangle } from "lucide-react";

interface Props {
  modelUrl?: string;
  onPointSelected?: (point: [number, number, number]) => void;
  measureMode?: boolean;
  pointA?: [number, number, number] | null;
  pointB?: [number, number, number] | null;
  label?: string;
}

export const MeshViewer: React.FC<Props> = ({
  modelUrl,
  onPointSelected,
  measureMode,
  pointA,
  pointB,
  label = "raw, uncalibrated (SfM units)"
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const [wireframe, setWireframe] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false); // Default to white scene background
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

  useEffect(() => {
    if (!mountRef.current) return;
    setLoadError(null);

    // 1. Scene setup (Default pure white background)
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(isDarkMode ? "#090d16" : "#ffffff");
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
    controls.minDistance = 0.1;
    controls.maxDistance = 200;
    controlsRef.current = controls;

    // 5. Lights (Full multi-source illumination for glTF PBR and unlit geometry)
    const hemiLight = new THREE.HemisphereLight(0xffffff, isDarkMode ? 0x222222 : 0xcccccc, 1.2);
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

    // 6. Floor Grid (Light grey grid on white background)
    const gridColor1 = isDarkMode ? 0x3b82f6 : 0x9ca3af;
    const gridColor2 = isDarkMode ? 0x1e293b : 0xe5e7eb;
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
                color: hasVertexColors ? 0xffffff : (isDarkMode ? 0x38bdf8 : 0x0284c7),
              });
              pcdObject = new THREE.Points(geometry, pcdMat);
            }

            group.add(pcdObject);

            const dist = maxDim * 1.6;
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
        gltfLoader.load(
          modelUrl,
          (gltf) => {
            while (group.children.length > 0) {
              group.remove(group.children[0]);
            }
            const model = gltf.scene;

            // Fix glTF materials: ensure metalness=0, roughness=1, double-sided, and sRGB color space
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
      // Never fall back to a placeholder box mesh in real mode
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

    // 11. Animation Loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
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
  }, [modelUrl, onPointSelected, isDarkMode]);

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

  // Update 3D marker spheres for Point A and Point B (High-contrast markers on white and dark backdrops)
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

      // Contrast outline ring
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
        const lineMat = new THREE.LineBasicMaterial({ color: 0x9333ea, linewidth: 3 }); // High-contrast purple
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

  return (
    <div className={`relative w-full h-[480px] rounded-2xl overflow-hidden border shadow-2xl transition-colors duration-200 ${
      isDarkMode ? "bg-[#090d16] border-dark-border" : "bg-white border-slate-200"
    }`}>
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Explicit Error Display Overlay (Never fall back to placeholder mesh) */}
      {loadError && (
        <div className="absolute inset-0 bg-dark-bg/90 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center z-20">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-3">
            <AlertTriangle className="w-6 h-6 text-rose-400" />
          </div>
          <h4 className="text-sm font-semibold text-white mb-1">Model Unavailable in Viewer</h4>
          <p className="text-xs text-rose-300 max-w-md font-mono bg-rose-950/40 border border-rose-900/50 p-2.5 rounded-xl mb-3">
            {loadError}
          </p>
          <p className="text-[11px] text-dark-muted max-w-sm">
            Real mode reconstructions strictly display verified assets. Placeholder meshes are disabled.
          </p>
        </div>
      )}

      {/* Top Banner Status & Mode */}
      <div className="absolute top-4 left-4 flex items-center space-x-2">
        <span className={`px-3 py-1 rounded-lg backdrop-blur border text-[11px] font-mono shadow-sm ${
          isDarkMode
            ? "bg-dark-card/90 border-dark-border/80 text-dark-muted"
            : "bg-white/90 border-slate-300 text-slate-700"
        }`}>
          {label}
        </span>
        {loadingModel && (
          <span className="px-2.5 py-1 rounded-lg bg-brand-500/20 border border-brand-500/40 text-[11px] text-brand-500 font-medium animate-pulse">
            Loading 3D asset...
          </span>
        )}
      </div>

      {/* Floating Action Toolbar */}
      <div className={`absolute top-4 right-4 flex items-center space-x-1.5 backdrop-blur p-1.5 rounded-xl border text-xs shadow-lg ${
        isDarkMode ? "bg-dark-card/90 border-dark-border" : "bg-white/90 border-slate-200"
      }`}>
        {/* White / Dark Mode Toggle */}
        <button
          onClick={() => setIsDarkMode(!isDarkMode)}
          className={`p-1.5 rounded-lg transition-colors ${
            isDarkMode ? "text-amber-400 hover:bg-dark-hover" : "text-slate-600 hover:bg-slate-100"
          }`}
          title={isDarkMode ? "Switch to white background" : "Switch to dark background"}
        >
          {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        <div className={`w-[1px] h-4 mx-0.5 ${isDarkMode ? "bg-dark-border" : "bg-slate-200"}`} />

        <button
          onClick={() => handleZoom(0.8)}
          className={`p-1.5 rounded-lg transition-colors ${
            isDarkMode ? "text-dark-muted hover:text-white hover:bg-dark-hover" : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
          }`}
          title="Zoom In (+)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <button
          onClick={() => handleZoom(1.25)}
          className={`p-1.5 rounded-lg transition-colors ${
            isDarkMode ? "text-dark-muted hover:text-white hover:bg-dark-hover" : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
          }`}
          title="Zoom Out (-)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <button
          onClick={handleResetView}
          className={`p-1.5 rounded-lg transition-colors ${
            isDarkMode ? "text-dark-muted hover:text-white hover:bg-dark-hover" : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
          }`}
          title="Reset Camera View"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        <div className={`w-[1px] h-4 mx-0.5 ${isDarkMode ? "bg-dark-border" : "bg-slate-200"}`} />

        <button
          onClick={() => setWireframe(!wireframe)}
          className={`px-2.5 py-1.5 rounded-lg flex items-center space-x-1.5 transition-all ${
            wireframe
              ? "bg-brand-500 text-white font-medium shadow-sm"
              : isDarkMode
              ? "text-dark-muted hover:text-white hover:bg-dark-hover"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
          }`}
          title="Toggle wireframe display"
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Wireframe</span>
        </button>

        <button
          onClick={() => setAutoRotate(!autoRotate)}
          className={`p-1.5 rounded-lg transition-all ${
            autoRotate
              ? "bg-brand-500 text-white"
              : isDarkMode
              ? "text-dark-muted hover:text-white hover:bg-dark-hover"
              : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
          }`}
          title="Toggle turntable auto-rotation"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>

      {/* Bottom instructions badge */}
      <div className="absolute bottom-4 left-4 flex items-center gap-2">
        {measureMode ? (
          <div className="bg-brand-600/90 backdrop-blur text-white px-3 py-1.5 rounded-xl text-xs flex items-center gap-2 shadow-lg">
            <Crosshair className="w-4 h-4 animate-spin text-brand-200" />
            <span>Click any 2 points on the 3D surface to calibrate physical scale</span>
          </div>
        ) : (
          <div className={`backdrop-blur px-3 py-1 rounded-lg text-[11px] border shadow-sm ${
            isDarkMode ? "bg-dark-card/80 text-dark-muted border-dark-border/60" : "bg-white/80 text-slate-600 border-slate-200"
          }`}>
            Rotate: Left Click + Drag | Pan: Right Click + Drag | Zoom: Scroll Wheel
          </div>
        )}
      </div>
    </div>
  );
};
