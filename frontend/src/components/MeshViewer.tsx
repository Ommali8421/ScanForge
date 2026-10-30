import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Eye, RotateCw, Crosshair, ZoomIn, ZoomOut, RefreshCw } from "lucide-react";

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
  const [loadingModel, setLoadingModel] = useState(false);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const meshGroupRef = useRef<THREE.Group | null>(null);
  const markersGroupRef = useRef<THREE.Group | null>(null);

  const initialCamPos = useRef<THREE.Vector3>(new THREE.Vector3(0, 2, 5));
  const initialTarget = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));

  useEffect(() => {
    if (!mountRef.current) return;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#090d16");
    sceneRef.current = scene;

    // 2. Camera setup
    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.05, 1000);
    camera.position.copy(initialCamPos.current);
    cameraRef.current = camera;

    // 3. Renderer setup
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
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

    // 5. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight1.position.set(5, 12, 7);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x93c5fd, 0.6);
    dirLight2.position.set(-5, 6, -5);
    scene.add(dirLight2);

    // 6. Subtle Floor Grid
    const grid = new THREE.GridHelper(10, 20, 0x3b82f6, 0x1e293b);
    grid.position.y = 0;
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
                roughness: 0.6,
                metalness: 0.1,
                side: THREE.DoubleSide,
              });
              pcdObject = new THREE.Mesh(geometry, mat);
            } else {
              // Point Cloud PLY
              const pcdMat = new THREE.PointsMaterial({
                size: Math.max(0.015, maxDim * 0.005),
                vertexColors: hasVertexColors,
                color: hasVertexColors ? 0xffffff : 0x38bdf8,
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
            console.warn("[MeshViewer] PLYLoader failed:", err);
            createProceduralFallback(group);
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
            console.warn("[MeshViewer] GLTFLoader failed:", err);
            createProceduralFallback(group);
            setLoadingModel(false);
          }
        );
      }
    } else {
      createProceduralFallback(group);
    }

    function createProceduralFallback(parentGroup: THREE.Group) {
      const roomGeo = new THREE.BoxGeometry(4, 2.6, 5);
      const roomMat = new THREE.MeshStandardMaterial({
        color: 0x94a3b8,
        side: THREE.BackSide,
        roughness: 0.8,
      });
      const roomMesh = new THREE.Mesh(roomGeo, roomMat);
      roomMesh.position.y = 1.3;
      parentGroup.add(roomMesh);
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
  }, [modelUrl, onPointSelected]);

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
      const matA = new THREE.MeshBasicMaterial({ color: 0x10b981 });
      const sphereA = new THREE.Mesh(geoA, matA);
      sphereA.position.set(pointA[0], pointA[1], pointA[2]);
      group.add(sphereA);
    }

    if (pointB) {
      const geoB = new THREE.SphereGeometry(0.08, 16, 16);
      const matB = new THREE.MeshBasicMaterial({ color: 0x3b82f6 });
      const sphereB = new THREE.Mesh(geoB, matB);
      sphereB.position.set(pointB[0], pointB[1], pointB[2]);
      group.add(sphereB);

      if (pointA) {
        const lineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, linewidth: 2 });
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
    <div className="relative w-full h-[480px] bg-dark-bg rounded-2xl overflow-hidden border border-dark-border shadow-2xl">
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Top Banner Status & Mode */}
      <div className="absolute top-4 left-4 flex items-center space-x-2">
        <span className="px-3 py-1 rounded-lg bg-dark-card/90 backdrop-blur border border-dark-border/80 text-[11px] font-mono text-dark-muted">
          {label}
        </span>
        {loadingModel && (
          <span className="px-2.5 py-1 rounded-lg bg-brand-500/20 border border-brand-500/40 text-[11px] text-brand-300 animate-pulse">
            Loading 3D asset...
          </span>
        )}
      </div>

      {/* Floating Action Toolbar */}
      <div className="absolute top-4 right-4 flex items-center space-x-1.5 bg-dark-card/90 backdrop-blur p-1.5 rounded-xl border border-dark-border text-xs shadow-lg">
        <button
          onClick={() => handleZoom(0.8)}
          className="p-1.5 rounded-lg text-dark-muted hover:text-white hover:bg-dark-hover transition-colors"
          title="Zoom In (+)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <button
          onClick={() => handleZoom(1.25)}
          className="p-1.5 rounded-lg text-dark-muted hover:text-white hover:bg-dark-hover transition-colors"
          title="Zoom Out (-)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <button
          onClick={handleResetView}
          className="p-1.5 rounded-lg text-dark-muted hover:text-white hover:bg-dark-hover transition-colors"
          title="Reset Camera View"
        >
          <RefreshCw className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-4 bg-dark-border mx-0.5" />

        <button
          onClick={() => setWireframe(!wireframe)}
          className={`px-2.5 py-1.5 rounded-lg flex items-center space-x-1.5 transition-all ${
            wireframe ? "bg-brand-500 text-white" : "text-dark-muted hover:text-white hover:bg-dark-hover"
          }`}
          title="Toggle wireframe display"
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Wireframe</span>
        </button>

        <button
          onClick={() => setAutoRotate(!autoRotate)}
          className={`p-1.5 rounded-lg transition-all ${
            autoRotate ? "bg-brand-500 text-white" : "text-dark-muted hover:text-white hover:bg-dark-hover"
          }`}
          title="Toggle turntable auto-rotation"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>

      {/* Bottom instructions badge */}
      <div className="absolute bottom-4 left-4 flex items-center gap-2">
        {measureMode ? (
          <div className="bg-brand-500/90 backdrop-blur text-white px-3 py-1.5 rounded-xl text-xs flex items-center gap-2 shadow-lg">
            <Crosshair className="w-4 h-4 animate-spin text-brand-200" />
            <span>Click any 2 points on the 3D surface to calibrate physical scale</span>
          </div>
        ) : (
          <div className="bg-dark-card/80 backdrop-blur text-dark-muted px-3 py-1 rounded-lg text-[11px] border border-dark-border/60">
            Rotate: Left Click + Drag | Pan: Right Click + Drag | Zoom: Scroll Wheel
          </div>
        )}
      </div>
    </div>
  );
};
