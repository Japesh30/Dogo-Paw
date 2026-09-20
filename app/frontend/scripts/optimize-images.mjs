/**
 * One-off asset pass: the artwork carried over from the original site was
 * straight off a camera (some files were 8 MB). This downscales everything to
 * sensible web dimensions in place, keeping the original filenames.
 *
 *   node scripts/optimize-images.mjs
 */
import { readdir, stat, rename, unlink } from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const DIR = path.resolve('src/assets/images')

// Wider budget for full-bleed banners, tighter for grid/cutout art.
const MAX_WIDTH = { banner1: 2000, default: 1600, logo: 512 }

const files = await readdir(DIR)
let before = 0
let after = 0

for (const file of files) {
  const ext = path.extname(file).toLowerCase()
  if (!['.jpg', '.jpeg', '.png'].includes(ext)) continue

  const src = path.join(DIR, file)
  const base = path.basename(file, ext)
  const original = (await stat(src)).size
  before += original

  const width = MAX_WIDTH[base] ?? MAX_WIDTH.default
  const tmp = path.join(DIR, `.tmp-${file}`)

  const pipeline = sharp(src).resize({
    width,
    withoutEnlargement: true,
  })

  // PNGs in this set are transparent cutouts, so they stay PNG.
  await (ext === '.png'
    ? pipeline.png({ compressionLevel: 9, palette: true })
    : pipeline.jpeg({ quality: 80, mozjpeg: true })
  ).toFile(tmp)

  const optimized = (await stat(tmp)).size
  if (optimized < original) {
    await unlink(src)
    await rename(tmp, src)
    after += optimized
  } else {
    await unlink(tmp)
    after += original
  }

  const kb = (n) => `${Math.round(n / 1024)} KB`
  console.log(`${file.padEnd(26)} ${kb(original).padStart(9)} -> ${kb(optimized)}`)
}

const mb = (n) => `${(n / 1024 / 1024).toFixed(1)} MB`
console.log(`\nTotal: ${mb(before)} -> ${mb(after)}`)
