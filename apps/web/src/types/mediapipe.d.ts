// Ambient module declaration for the MediaPipe tasks-vision bundle loaded
// dynamically from a CDN at runtime. We use `any` here because TypeScript
// cannot resolve types for an https:// import specifier.
declare module "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mod: any;
  export = mod;
}
