import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { Eye, RotateCw, Crosshair } from "lucide-react";

interface Props {
  modelUrl?: string;
  onPointSelected?: (point: [number, number, number]) => void;
  measureMode?: boolean;
  pointA?: [number, number, number] | null;
  pointB?: [number, number, number] | null;
}

export const MeshViewer: React.FC<Props> = ({
  modelUrl,
  onPointSelected,
  measureMode,
  pointA,
  pointB,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const [wireframe, setWireframe] = useState(false);
  const [autoRotate, setAutoRotate] = useState(false);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const meshGroupRef = useRef<THREE.Group | null>(null);
  const markersGroupRef = useRef<THREE.Group | null>(null);

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
    camera.position.set(4, 3, 5);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;

    // 3. Renderer setup
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight1.position.set(5, 10, 7);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x60a5fa, 0.5);
    dirLight2.position.set(-5, 5, -5);
    scene.add(dirLight2);

    // 5. Grid Helper
    const grid = new THREE.GridHelper(10, 20, 0x3b82f6, 0x1e293b);
    grid.position.y = 0;
    scene.add(grid);

    // 6. Mesh group & Markers group
    const group = new THREE.Group();
    meshGroupRef.current = group;
    scene.add(group);

    const markersGroup = new THREE.Group();
    markersGroupRef.current = markersGroup;
    scene.add(markersGroup);

    // Spherical orbit controls state
    let isDragging = false;
    let prevMouse = { x: 0, y: 0 };
    let spherical = { radius: 6, theta: 0.8, phi: 1.1 };
    let target = new THREE.Vector3(0, 0, 0);

    const updateCameraPos = () => {
      camera.position.x = target.x + spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      camera.position.y = target.y + spherical.radius * Math.cos(spherical.phi);
      camera.position.z = target.z + spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      camera.lookAt(target);
    };
    updateCameraPos();

    // 7. Load real GLB model or fall back to procedural geometry
    if (modelUrl) {
      const loader = new GLTFLoader();
      loader.load(
        modelUrl,
        (gltf) => {
          // Clear procedural content
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

          spherical.radius = maxDim * 1.8;
          target.set(0, 0, 0);
          updateCameraPos();
        },
        undefined,
        (err) => {
          console.warn("[MeshViewer] GLTFLoader failed to load modelUrl:", err);
          createProceduralFallback(group);
        }
      );
    } else {
      createProceduralFallback(group);
    }

    function createProceduralFallback(parentGroup: THREE.Group) {
      // Room Box geometry (walls and floor)
      const roomGeo = new THREE.BoxGeometry(4, 2.6, 5);
      const roomMat = new THREE.MeshStandardMaterial({
        color: 0x94a3b8,
        side: THREE.BackSide,
        roughness: 0.8,
      });
      const roomMesh = new THREE.Mesh(roomGeo, roomMat);
      roomMesh.position.y = 1.3;
      parentGroup.add(roomMesh);

      // Table box
      const tableGeo = new THREE.BoxGeometry(1.2, 0.75, 0.8);
      const tableMat = new THREE.MeshStandardMaterial({ color: 0x3b82f6, roughness: 0.5 });
      const tableMesh = new THREE.Mesh(tableGeo, tableMat);
      tableMesh.position.set(0, 0.375, 0);
      parentGroup.add(tableMesh);

      // Chair box
      const chairGeo = new THREE.BoxGeometry(0.4, 0.45, 0.4);
      const chairMat = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.6 });
      const chairMesh = new THREE.Mesh(chairGeo, chairMat);
      chairMesh.position.set(1.0, 0.225, 0.4);
      parentGroup.add(chairMesh);
    }

    // 8. Interactive orbit controls
    const handleMouseDown = (e: MouseEvent) => {
      isDragging = true;
      prevMouse = { x: e.clientX, y: e.clientY };
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - prevMouse.x;
      const dy = e.clientY - prevMouse.y;
      prevMouse = { x: e.clientX, y: e.clientY };

      spherical.theta -= dx * 0.008;
      spherical.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.05, spherical.phi - dy * 0.008));
      updateCameraPos();
    };

    const handleMouseUp = () => {
      isDragging = false;
    };

    const handleWheel = (e: WheelEvent) => {
      spherical.radius = Math.max(0.5, Math.min(40, spherical.radius + e.deltaY * 0.005));
      updateCameraPos();
    };

    const dom = renderer.domElement;
    dom.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    dom.addEventListener("wheel", handleWheel);

    // Raycasting for point picking
    const raycaster = new THREE.Raycaster();
    const mouseCoord = new THREE.Vector2();

    const handleClick = (e: MouseEvent) => {
      if (!onPointSelected) return;
      const rect = dom.getBoundingClientRect();
      mouseCoord.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouseCoord.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouseCoord, camera);
      const intersects = raycaster.intersectObjects(group.children, true);
      if (intersects.length > 0) {
        const pt = intersects[0].point;
        onPointSelected([parseFloat(pt.x.toFixed(3)), parseFloat(pt.y.toFixed(3)), parseFloat(pt.z.toFixed(3))]);
      }
    };
    dom.addEventListener("click", handleClick);

    // Resize handler
    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // Animation loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      if (autoRotate) {
        spherical.theta += 0.003;
        updateCameraPos();
      }
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      dom.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      dom.removeEventListener("wheel", handleWheel);
      dom.removeEventListener("click", handleClick);
      window.removeEventListener("resize", handleResize);
      if (dom.parentElement) {
        dom.parentElement.removeChild(dom);
      }
      renderer.dispose();
    };
  }, [modelUrl, autoRotate, onPointSelected]);

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
      const matA = new THREE.MeshBasicMaterial({ color: 0x10b981 }); // emerald
      const sphereA = new THREE.Mesh(geoA, matA);
      sphereA.position.set(pointA[0], pointA[1], pointA[2]);
      group.add(sphereA);
    }

    if (pointB) {
      const geoB = new THREE.SphereGeometry(0.08, 16, 16);
      const matB = new THREE.MeshBasicMaterial({ color: 0x3b82f6 }); // blue
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

  return (
    <div className="relative w-full h-[450px] bg-dark-bg rounded-2xl overflow-hidden border border-dark-border shadow-xl">
      <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Floating Toolbar */}
      <div className="absolute top-4 right-4 flex items-center space-x-1.5 bg-dark-card/90 backdrop-blur p-1.5 rounded-xl border border-dark-border text-xs">
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

      {measureMode && (
        <div className="absolute bottom-4 left-4 bg-brand-500/90 backdrop-blur text-white px-3 py-1.5 rounded-xl text-xs flex items-center gap-2 shadow-lg">
          <Crosshair className="w-4 h-4 animate-spin text-brand-200" />
          <span>Click any 2 points on the 3D surface to calibrate physical scale</span>
        </div>
      )}
    </div>
  );
};
