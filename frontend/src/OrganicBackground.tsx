import { useEffect, useMemo, useRef } from 'react'
import { AdaptiveDpr, OrthographicCamera } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const fragmentShader = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform float uTime;
  uniform vec2 uResolution;
  uniform vec2 uPointer;

  float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
               mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
  }

  float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;
    for (int i = 0; i < 4; i++) {
      value += amplitude * noise(p);
      p = p * 2.03 + vec2(13.7, 9.2);
      amplitude *= 0.5;
    }
    return value;
  }

  float ellipse(vec2 p, vec2 center, vec2 radius) {
    vec2 q = (p - center) / radius;
    return (length(q) - 1.0) * min(radius.x, radius.y);
  }

  float smoothUnion(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
  }

  float blobField(vec2 p) {
    // Keep the plasma cluster framed with visible black space around it.
    p *= 1.24;
    float t = uTime;
    vec2 drift = uPointer * 0.075;
    float a = ellipse(p, vec2(-0.40 + drift.x + 0.045 * sin(t * 0.22), 0.00 + drift.y + 0.055 * cos(t * 0.19)), vec2(0.46, 0.54));
    float b = ellipse(p, vec2( 0.03 + drift.x * 0.7 + 0.055 * cos(t * 0.17 + 1.2), -0.06 + drift.y * 0.7 + 0.045 * sin(t * 0.20)), vec2(0.54, 0.49));
    float c = ellipse(p, vec2( 0.43 + drift.x * 0.8 + 0.04 * sin(t * 0.18 + 2.0),  0.03 + drift.y * 0.8 + 0.06 * cos(t * 0.16)), vec2(0.43, 0.52));
    float d = ellipse(p, vec2(-0.04 + drift.x * 0.5 + 0.04 * sin(t * 0.15 + 3.0),  0.40 + drift.y * 0.5 + 0.045 * cos(t * 0.21)), vec2(0.38, 0.34));
    return smoothUnion(smoothUnion(a, b, 0.24), smoothUnion(c, d, 0.21), 0.22);
  }

  vec3 plasmaPalette(float x) {
    vec3 navy = vec3(0.012, 0.035, 0.24);
    vec3 blue = vec3(0.035, 0.20, 0.92);
    vec3 violet = vec3(0.34, 0.075, 0.92);
    vec3 magenta = vec3(0.83, 0.035, 0.66);
    vec3 coral = vec3(1.0, 0.11, 0.28);
    vec3 color = mix(navy, blue, smoothstep(0.00, 0.23, x));
    color = mix(color, violet, smoothstep(0.18, 0.47, x));
    color = mix(color, magenta, smoothstep(0.42, 0.72, x));
    return mix(color, coral, smoothstep(0.70, 1.0, x));
  }

  void main() {
    float aspect = uResolution.x / max(uResolution.y, 1.0);
    vec2 p = (vUv - 0.5) * vec2(aspect, 1.0);
    float time = uTime;

    // Two low-frequency noise fields gently warp the silhouette like moving liquid.
    vec2 warp = vec2(
      fbm(p * 2.5 + vec2(time * 0.035, -time * 0.024)),
      fbm(p * 2.5 + vec2(7.1, 3.7) + vec2(-time * 0.027, time * 0.031))
    ) - 0.5;
    vec2 fluidP = p + warp * 0.075;
    float distanceField = blobField(fluidP);
    float inside = 1.0 - smoothstep(-0.012, 0.045, distanceField);
    float flow = fbm(fluidP * 3.4 + vec2(time * 0.07, -time * 0.052));
    float ribbons = sin(fluidP.x * 5.2 - fluidP.y * 3.4 + flow * 7.0 - time * 0.19);
    float colorPosition = clamp(0.49 + ribbons * 0.22 + (flow - 0.48) * 0.75 + fluidP.y * 0.12, 0.0, 1.0);

    vec3 color = plasmaPalette(colorPosition);
    float coreLight = pow(max(0.0, 1.0 - length((fluidP - vec2(-0.28, 0.18)) * vec2(1.5, 1.8))), 2.0);
    float hotLight = pow(max(0.0, 1.0 - length((fluidP - vec2(0.42, -0.18)) * vec2(1.7, 1.4))), 3.0);
    color *= 0.62 + flow * 0.55;
    color += vec3(0.12, 0.24, 0.78) * coreLight * 0.58;
    color += vec3(0.95, 0.10, 0.31) * hotLight * 0.38;

    float edgeLight = exp(-abs(distanceField) * 17.0);
    float innerRim = exp(-max(-distanceField, 0.0) * 5.0) * inside;
    color += vec3(0.42, 0.31, 1.0) * edgeLight * 0.24;
    color += vec3(0.04, 0.46, 0.92) * innerRim * (0.10 + flow * 0.12);

    float outerGlow = exp(-max(distanceField, 0.0) * 5.0) * (1.0 - inside);
    vec3 glowColor = plasmaPalette(clamp(colorPosition + 0.1, 0.0, 1.0));
    vec3 finalColor = color * inside + glowColor * outerGlow * 0.20;

    // Fine moving grain breaks up the gradient and keeps the plasma surface tactile.
    float grain = hash(gl_FragCoord.xy + fract(time * 0.07) * 113.0) - 0.5;
    finalColor += grain * 0.018 * (inside + outerGlow * 0.25);
    gl_FragColor = vec4(finalColor, 1.0);
  }
`

const particleVertexShader = /* glsl */ `
  attribute float aSize;
  attribute vec3 aColor;
  varying vec3 vColor;
  void main() {
    vColor = aColor;
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * viewPosition;
    gl_PointSize = aSize;
  }
`

const particleFragmentShader = /* glsl */ `
  precision highp float;
  varying vec3 vColor;
  void main() {
    float radius = length(gl_PointCoord - vec2(0.5));
    float core = 1.0 - smoothstep(0.12, 0.5, radius);
    float halo = exp(-radius * 11.0) * 0.45;
    float alpha = core + halo;
    if (alpha < 0.025) discard;
    gl_FragColor = vec4(vColor * (1.0 + halo), alpha);
  }
`

const ORBIT_COUNT = 104
const MAX_LINKS = 260
type OrbitSeed = { angle: number; radius: number; speed: number; phase: number; eccentricity: number; size: number; color: THREE.Color }

function makeOrbitSeeds(): OrbitSeed[] {
  const palette = ['#a58aff', '#7b8dff', '#65d9ff', '#e58cff', '#f070bc']
  return Array.from({ length: ORBIT_COUNT }, (_, i) => ({
    angle: (i / ORBIT_COUNT) * Math.PI * 2 + (Math.random() - 0.5) * 0.25,
    radius: 0.36 + Math.random() * 0.42,
    speed: (0.035 + Math.random() * 0.07) * (i % 2 ? 1 : -1),
    phase: Math.random() * Math.PI * 2,
    eccentricity: 0.55 + Math.random() * 0.28,
    size: 1.8 + Math.random() * 2.2,
    color: new THREE.Color(palette[Math.floor(Math.random() * palette.length)]),
  }))
}

function OrbitingNodes() {
  const { viewport } = useThree()
  const seeds = useMemo(makeOrbitSeeds, [])
  const pointsGeometry = useMemo(() => new THREE.BufferGeometry(), [])
  const linksGeometry = useMemo(() => new THREE.BufferGeometry(), [])
  const pointPositions = useMemo(() => new THREE.BufferAttribute(new Float32Array(ORBIT_COUNT * 3), 3), [])
  const pointColors = useMemo(() => new THREE.BufferAttribute(new Float32Array(ORBIT_COUNT * 3), 3), [])
  const pointSizes = useMemo(() => new THREE.BufferAttribute(new Float32Array(ORBIT_COUNT), 1), [])
  const linkPositions = useMemo(() => new THREE.BufferAttribute(new Float32Array(MAX_LINKS * 2 * 3), 3), [])

  useEffect(() => {
    pointsGeometry.setAttribute('position', pointPositions)
    pointsGeometry.setAttribute('aColor', pointColors)
    pointsGeometry.setAttribute('aSize', pointSizes)
    linksGeometry.setAttribute('position', linkPositions)
    return () => { pointsGeometry.dispose(); linksGeometry.dispose() }
  }, [linkPositions, linksGeometry, pointColors, pointPositions, pointSizes, pointsGeometry])

  useFrame((state) => {
    const time = state.clock.elapsedTime
    const height = viewport.height
    const positions = pointPositions.array as Float32Array
    const colors = pointColors.array as Float32Array
    const sizes = pointSizes.array as Float32Array
    for (let i = 0; i < ORBIT_COUNT; i++) {
      const seed = seeds[i]
      const angle = seed.angle + time * seed.speed
      const radius = seed.radius + Math.sin(time * 0.42 + seed.phase) * 0.035
      positions[i * 3] = Math.cos(angle) * radius * height + Math.sin(time * 0.18 + seed.phase) * height * 0.035
      positions[i * 3 + 1] = Math.sin(angle) * radius * seed.eccentricity * height + Math.cos(time * 0.16 + seed.phase) * height * 0.045
      positions[i * 3 + 2] = 0.08 + Math.sin(time * 0.25 + seed.phase) * 0.025
      colors[i * 3] = seed.color.r
      colors[i * 3 + 1] = seed.color.g
      colors[i * 3 + 2] = seed.color.b
      sizes[i] = seed.size * (0.82 + 0.18 * Math.sin(time * 1.5 + seed.phase))
    }
    pointPositions.needsUpdate = true
    pointColors.needsUpdate = true
    pointSizes.needsUpdate = true

    const edges = linkPositions.array as Float32Array
    let edgeCount = 0
    for (let i = 0; i < ORBIT_COUNT && edgeCount < MAX_LINKS; i++) {
      for (let j = i + 1; j < ORBIT_COUNT && edgeCount < MAX_LINKS; j++) {
        const dx = positions[i * 3] - positions[j * 3]
        const dy = positions[i * 3 + 1] - positions[j * 3 + 1]
        const distance = dx * dx + dy * dy
        if (distance < height * height * 0.018) {
          const offset = edgeCount * 6
          edges[offset] = positions[i * 3]; edges[offset + 1] = positions[i * 3 + 1]; edges[offset + 2] = positions[i * 3 + 2]
          edges[offset + 3] = positions[j * 3]; edges[offset + 4] = positions[j * 3 + 1]; edges[offset + 5] = positions[j * 3 + 2]
          edgeCount++
        }
      }
    }
    linkPositions.needsUpdate = true
    linksGeometry.setDrawRange(0, edgeCount * 2)
  })

  return (
    <>
      <lineSegments geometry={linksGeometry} frustumCulled={false}>
        <lineBasicMaterial color="#9b85ff" transparent opacity={0.14} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>
      <points geometry={pointsGeometry} frustumCulled={false}>
        <shaderMaterial
          vertexShader={particleVertexShader}
          fragmentShader={particleFragmentShader}
          transparent
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>
    </>
  )
}

function PlasmaPlane() {
  const materialRef = useRef<THREE.ShaderMaterial>(null)
  const pointer = useRef(new THREE.Vector2())
  const target = useRef(new THREE.Vector2())
  const { viewport, size } = useThree()

  const uniforms = useMemo(() => ({
    uTime: { value: 0 },
    uResolution: { value: new THREE.Vector2(1, 1) },
    uPointer: { value: new THREE.Vector2() },
  }), [])

  useEffect(() => {
    const updatePointer = (event: PointerEvent) => {
      target.current.set(
        (event.clientX / window.innerWidth - 0.5) * 2,
        -(event.clientY / window.innerHeight - 0.5) * 2,
      )
    }
    window.addEventListener('pointermove', updatePointer, { passive: true })
    return () => window.removeEventListener('pointermove', updatePointer)
  }, [])

  useFrame((state, delta) => {
    if (!materialRef.current) return
    const shader = materialRef.current
    shader.uniforms.uTime.value = state.clock.elapsedTime
    pointer.current.lerp(target.current, 1 - Math.exp(-delta * 2.2))
    shader.uniforms.uPointer.value.copy(pointer.current)
    shader.uniforms.uResolution.value.set(size.width, size.height)
  })

  return (
    <mesh scale={[viewport.width / 2, viewport.height / 2, 1]}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        depthWrite={false}
        depthTest={false}
      />
    </mesh>
  )
}

/** Full-screen procedural plasma backdrop. Place once near the app root. */
export function OrganicBackground() {
  return (
    <div className="organic-background" aria-hidden="true">
      <Canvas
        dpr={[1, 1.35]}
        frameloop="always"
        gl={{ alpha: false, antialias: false, powerPreference: 'low-power' }}
        orthographic
        camera={{ position: [0, 0, 10], zoom: 100 }}
      >
        <color attach="background" args={['#000000']} />
        <OrthographicCamera makeDefault position={[0, 0, 10]} zoom={100} />
        <PlasmaPlane />
        <OrbitingNodes />
        <AdaptiveDpr pixelated />
      </Canvas>
    </div>
  )
}

export default OrganicBackground
