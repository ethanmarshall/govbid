import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

// Renders the triangle mesh the backend builds from the STEP file (inches).
export default function StepViewer({ mesh, height = 340 }) {
  const box = useRef()

  useEffect(() => {
    const el = box.current
    if (!el || !mesh?.positions?.length) return
    const w = el.clientWidth || 500
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.setSize(w, height)
    el.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.Float32BufferAttribute(mesh.positions, 3))
    geom.setIndex(mesh.indices)
    geom.computeVertexNormals()
    geom.computeBoundingSphere()
    const { center, radius } = geom.boundingSphere
    geom.translate(-center.x, -center.y, -center.z)

    const part = new THREE.Mesh(geom, new THREE.MeshStandardMaterial({ color: 0xb8c2cc, metalness: 0.35, roughness: 0.45, side: THREE.DoubleSide }))
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 25), new THREE.LineBasicMaterial({ color: 0x334155 }))
    scene.add(part, edges)
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 1.6))
    const sun = new THREE.DirectionalLight(0xffffff, 1.4)
    sun.position.set(1, 2, 3)
    scene.add(sun)

    const camera = new THREE.PerspectiveCamera(35, w / height, radius / 100, radius * 100)
    camera.up.set(0, 0, 1)
    camera.position.set(radius * 2.2, -radius * 2.6, radius * 1.8)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true

    let frame
    const tick = () => { controls.update(); renderer.render(scene, camera); frame = requestAnimationFrame(tick) }
    tick()
    const ro = new ResizeObserver(() => {
      const nw = el.clientWidth
      if (!nw) return
      renderer.setSize(nw, height)
      camera.aspect = nw / height
      camera.updateProjectionMatrix()
    })
    ro.observe(el)
    return () => {
      cancelAnimationFrame(frame)
      ro.disconnect()
      controls.dispose()
      geom.dispose()
      renderer.dispose()
      el.removeChild(renderer.domElement)
    }
  }, [mesh, height])

  return <div ref={box} className="viewer" style={{ height }} title="Drag to rotate, scroll to zoom, right-drag to pan" />
}
