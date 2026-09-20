/**
 * Builds one gallery photo per seeded dog into `public/dogs/`.
 *
 *   npm run build:dog-photos
 *
 * The 18 dogs in `backend/seed.py` are a synthetic dataset — they have no
 * photographs of their own. Rather than call out to a stock-photo service (which
 * would break the moment the laptop is offline, i.e. during a demo), this uses
 * the ten real rescue-dog photographs that already ship with the site and were
 * carried over from the original static build.
 *
 * Ten photos, eighteen dogs, so some sources are reused. To stop a reused source
 * from looking like a copy-paste in the grid, each dog gets its own *variant* of
 * the crop:
 *
 *   0  attention crop           — sharp finds the busiest region, i.e. the dog
 *   1  attention crop, mirrored — reads as a different photo at card size
 *   2  attention crop, zoomed   — tighter framing on the same subject
 *
 * Mirroring and zooming are used rather than a fixed gravity ('north', 'east'…)
 * because a fixed gravity can crop the dog straight out of the frame; these two
 * cannot.
 *
 * Sources are grouped by build, so a "small" dog never gets the photo of a
 * shepherd-sized one. Assignments are also chosen to suit each dog's
 * temperament where the pool allows it — the calm senior gets the sleeping dog,
 * the puppies get the puppies.
 */
import { mkdir, readdir, stat, unlink } from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const SOURCE_DIR = path.resolve('src/assets/images')
const OUT_DIR = path.resolve('public/dogs')

const WIDTH = 900
const HEIGHT = 675 // 4:3, matches the card and profile aspect ratios
const ZOOM = 1.18 // variant 2's tighter framing

// dog_id -> [source file, variant]. Kept in dog_id order so it reads against
// the DOGS table in backend/seed.py.
const ASSIGNMENTS = {
  // large — the three biggest-framed photos
  1: ['vol1.jpg', 0], // Bruno    energetic
  4: ['foster2.jpg', 0], // Rocky    independent, sleeping alone
  6: ['vol1.jpg', 1], // Simba    protective
  8: ['foster5.jpg', 0], // Max      calm, medical needs
  11: ['foster2.jpg', 1], // Rex      stubborn
  14: ['foster5.jpg', 1], // Buddy    friendly
  16: ['foster2.jpg', 2], // Shadow   independent
  18: ['vol1.jpg', 2], // Thor     energetic

  // medium
  2: ['tommy.jpg', 0], // Tommy    — the photo is literally of a dog named Tommy
  5: ['foster3.jpg', 0], // Bella    friendly
  10: ['foster3.jpg', 1], // Zoe      gentle
  12: ['tommy.jpg', 1], // Milo     energetic
  13: ['vol3.jpg', 0], // Nala     8 years old, calm — the resting senior

  // small
  3: ['foster4.jpg', 0], // Luna     calm — the curled-up sleeper
  7: ['foster6.jpg', 0], // Coco     10 months, playful — the puppy
  9: ['foster1.jpg', 0], // Daisy    shy — the uncertain puppy
  15: ['vol2.jpg', 0], // Pixie    anxious
  17: ['vol2.jpg', 1], // Ginger   playful
}

async function build(dogId, [file, variant]) {
  const src = path.join(SOURCE_DIR, file)
  const out = path.join(OUT_DIR, `dog-${String(dogId).padStart(2, '0')}.jpg`)

  // `attention` picks the region of highest entropy, which on these photos is
  // reliably the dog rather than the pavement behind it.
  const zoomed = variant === 2
  let pipeline = sharp(src).resize({
    width: Math.round(WIDTH * (zoomed ? ZOOM : 1)),
    height: Math.round(HEIGHT * (zoomed ? ZOOM : 1)),
    fit: 'cover',
    position: sharp.strategy.attention,
  })

  if (zoomed) {
    pipeline = pipeline.extract({
      left: Math.round((WIDTH * ZOOM - WIDTH) / 2),
      top: Math.round((HEIGHT * ZOOM - HEIGHT) / 2),
      width: WIDTH,
      height: HEIGHT,
    })
  }

  if (variant === 1) pipeline = pipeline.flop()

  await pipeline.jpeg({ quality: 78, mozjpeg: true }).toFile(out)
  return (await stat(out)).size
}

await mkdir(OUT_DIR, { recursive: true })

// Clear stale output so a removed assignment cannot leave an orphan behind.
for (const existing of await readdir(OUT_DIR)) {
  if (existing.endsWith('.jpg')) await unlink(path.join(OUT_DIR, existing))
}

let total = 0
const ids = Object.keys(ASSIGNMENTS)
  .map(Number)
  .sort((a, b) => a - b)

for (const id of ids) {
  const bytes = await build(id, ASSIGNMENTS[id])
  total += bytes
  const [file, variant] = ASSIGNMENTS[id]
  const tag = ['', ' (mirrored)', ' (zoomed)'][variant]
  console.log(
    `dog-${String(id).padStart(2, '0')}.jpg  ${String(Math.round(bytes / 1024)).padStart(4)} KB  <- ${file}${tag}`,
  )
}

console.log(
  `\n${ids.length} photos, ${(total / 1024 / 1024).toFixed(2)} MB total -> public/dogs/`,
)
