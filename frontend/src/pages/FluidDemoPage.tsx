import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowUpRight, Fingerprint, ShieldCheck } from 'lucide-react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'
import type { PointerEvent as ReactPointerEvent } from 'react'
import OrganicBackground from '../OrganicBackground'

export default function FluidDemoPage() {
  const mouseX = useMotionValue(0.5)
  const mouseY = useMotionValue(0.5)
  const rotateY = useSpring(useTransform(mouseX, [0, 1], [-3.5, 3.5]), { stiffness: 110, damping: 20 })
  const rotateX = useSpring(useTransform(mouseY, [0, 1], [2.8, -2.8]), { stiffness: 110, damping: 20 })
  const trackText = (event: ReactPointerEvent<HTMLHeadingElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    const x = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width))
    const y = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height))
    mouseX.set(x)
    mouseY.set(y)
    event.currentTarget.style.setProperty('--pointer-x', `${x * 100}%`)
    event.currentTarget.style.setProperty('--pointer-y', `${y * 100}%`)
  }
  const resetText = (event: ReactPointerEvent<HTMLHeadingElement>) => {
    mouseX.set(0.5)
    mouseY.set(0.5)
    event.currentTarget.style.setProperty('--pointer-x', '50%')
    event.currentTarget.style.setProperty('--pointer-y', '50%')
  }

  return (
    <main className="fluid-demo">
      <OrganicBackground />
      <div className="fluid-demo-top">
        <Link to="/" className="demo-back"><ArrowLeft size={15} /> Back to workspace</Link>
        <span className="demo-status"><i /> WEBGL PLASMA STUDY</span>
      </div>
      <motion.section className="demo-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: 'easeOut' }}>
        <div className="demo-card-mark"><Fingerprint size={20} /></div>
        <div className="demo-eyebrow"><span /> SIGNAL CONVERGENCE / 001</div>
        <motion.h1
          onPointerMove={trackText}
          onPointerLeave={resetText}
          style={{ rotateX, rotateY, transformPerspective: 800, transformStyle: 'preserve-3d' }}
        >Trace the<br /><em>invisible.</em></motion.h1>
        <p>A living map of subtle connections. Find the signal beneath the noise.</p>
        <Link to="/" className="demo-cta">Enter workspace <ArrowUpRight size={15} /></Link>
        <div className="demo-card-foot"><ShieldCheck size={14} /> EVIDENCE-LED INTELLIGENCE <span>·</span> LOCAL RESEARCH</div>
      </motion.section>
      <div className="demo-side-note"><span>FIG 01</span><i /> PROCEDURAL PLASMA FIELD</div>
      <div className="demo-coordinates">LATENCY <b>LOW</b><br />RESPONSE <b>ACTIVE</b></div>
    </main>
  )
}
