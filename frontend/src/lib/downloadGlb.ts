import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";

interface MetadataJson {
  object_name?: string;
  object_type?: string;
  transform?: {
    location?: number[];
    rotation_euler?: number[];
    scale?: number[];
  };
  materials?: MaterialInfo[];
  [key: string]: unknown;
}

interface MaterialInfo {
  name?: string;
  diffuse_color?: number[];
  roughness?: number;
  metallic?: number;
  use_nodes?: boolean;
  nodes?: NodeInfo[];
  [key: string]: unknown;
}

interface NodeInfo {
  name?: string;
  type?: string;
  inputs?: Record<string, unknown>;
  [key: string]: unknown;
}

interface PolygonData {
  vertices: number[];
  loop_start: number;
  loop_total: number;
}

interface GeometryJson {
  vertices?: number[][];
  normals?: number[][];
  polygons?: PolygonData[];
  uv_layers?: { name: string; data: number[][] }[];
  [key: string]: unknown;
}

function downloadArrayBuffer(filename: string, arrayBuffer: ArrayBuffer) {
  const blob = new Blob([arrayBuffer], { type: "model/gltf-binary" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function getPrincipledInputs(metadata: MetadataJson) {
  const material = metadata?.materials?.[0];
  const principled = material?.nodes?.find(
    (node) => node.name === "Principled BSDF"
  );

  return {
    materialName: material?.name || "Material",
    baseColor:
      (principled?.inputs?.["Base Color"] as number[]) ||
      material?.diffuse_color ||
      [0.8, 0.8, 0.8, 1.0],
    roughness:
      (principled?.inputs?.["Roughness"] as number) ?? material?.roughness ?? 0.5,
    metalness:
      (principled?.inputs?.["Metallic"] as number) ?? material?.metallic ?? 0.0,
    alpha: (principled?.inputs?.["Alpha"] as number) ?? 1.0,
  };
}

function buildMaterial(metadata: MetadataJson): THREE.MeshStandardMaterial {
  const { materialName, baseColor, roughness, metalness, alpha } =
    getPrincipledInputs(metadata);

  return new THREE.MeshStandardMaterial({
    name: materialName,
    color: new THREE.Color(baseColor[0], baseColor[1], baseColor[2]),
    roughness,
    metalness,
    transparent: alpha < 1,
    opacity: alpha,
    side: THREE.DoubleSide,
  });
}

function triangulateFace(faceVerts: number[]): number[][] {
  const triangles: number[][] = [];
  for (let i = 1; i < faceVerts.length - 1; i++) {
    triangles.push([faceVerts[0], faceVerts[i], faceVerts[i + 1]]);
  }
  return triangles;
}

function buildMesh(
  metadata: MetadataJson,
  geometry: GeometryJson
): THREE.Mesh {
  const positions: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  const srcVerts = geometry.vertices || [];
  const srcNormals = geometry.normals || [];
  const srcPolygons = geometry.polygons || [];
  const srcUVs = geometry.uv_layers?.[0]?.data || [];

  let idx = 0;

  for (const polygon of srcPolygons) {
    const faceVerts = polygon.vertices || [];
    const loopStart = polygon.loop_start || 0;
    if (faceVerts.length < 3) continue;

    for (const tri of triangulateFace(faceVerts)) {
      for (const vertexIndex of tri) {
        const cornerIndex = faceVerts.indexOf(vertexIndex);
        const uvIndex = loopStart + cornerIndex;

        const v = srcVerts[vertexIndex];
        positions.push(v[0], v[1], v[2]);

        const n = srcNormals[vertexIndex];
        if (n) normals.push(n[0], n[1], n[2]);

        const uv = srcUVs[uvIndex];
        if (uv) uvs.push(uv[0], uv[1]);

        indices.push(idx++);
      }
    }
  }

  const geom = new THREE.BufferGeometry();
  geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geom.setIndex(indices);

  if (normals.length === positions.length) {
    geom.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  } else {
    geom.computeVertexNormals();
  }

  if (uvs.length * 3 === positions.length * 2) {
    geom.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  }

  const material = buildMaterial(metadata);
  const mesh = new THREE.Mesh(geom, material);

  mesh.name = metadata.object_name || "Object";

  const t = metadata.transform || {};
  const loc = t.location || [0, 0, 0];
  const rot = t.rotation_euler || [0, 0, 0];
  const scl = t.scale || [1, 1, 1];
  mesh.position.set(loc[0], loc[1], loc[2]);
  mesh.rotation.set(rot[0], rot[1], rot[2]);
  mesh.scale.set(scl[0], scl[1], scl[2]);

  geom.computeBoundingBox();
  geom.computeBoundingSphere();

  return mesh;
}

/**
 * Build a Three.js mesh from metadata + geometry JSON and trigger a GLB download.
 */
export function downloadGlbFromStoredJson(
  metadataJson: MetadataJson,
  geometryJson: GeometryJson,
  filename = "model.glb"
) {
  const mesh = buildMesh(metadataJson, geometryJson);
  const exporter = new GLTFExporter();

  exporter.parse(
    mesh,
    (result) => {
      if (result instanceof ArrayBuffer) {
        downloadArrayBuffer(filename, result);
      } else {
        console.error("Expected binary GLB output but got JSON glTF.");
      }
    },
    (error) => {
      console.error("GLB export failed:", error);
    },
    { binary: true }
  );
}
