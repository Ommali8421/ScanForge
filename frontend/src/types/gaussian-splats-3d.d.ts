declare module '@mkkellogg/gaussian-splats-3d' {
  export const SceneFormat: {
    Splat: number;
    Ply: number;
    KSplat: number;
    Ksplat: number;
    Spz: number;
  };
  export const SplatRenderMode: {
    Standard: number;
  };
  export class Viewer {
    constructor(options: any);
    addSplatScene(path: string, options?: any): Promise<any>;
    dispose(): void;
    camera: any;
    controls: any;
    splatMesh: any;
  }
}

