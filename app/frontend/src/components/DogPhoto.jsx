import DogAvatar from './DogAvatar'

/**
 * A dog's photo, with the drawn avatar as the fallback for any dog that has no
 * `photo_url` — a hand-added row, or a file that failed to load.
 *
 * The photographs are the rescue's own, cropped one per dog by
 * `npm run build:dog-photos`. The 18 dogs in the dataset are synthetic, so the
 * caption marks them as representative rather than letting a visitor believe
 * they are looking at that specific animal.
 */
export default function DogPhoto({
  dog,
  className = '',
  sizes,
  eager = false,
  caption = true,
}) {
  const src = dog?.photo_url
  const id = dog?.dog_id ?? 0

  if (!src) {
    return <DogAvatar seed={id} className={className} />
  }

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <img
        src={src}
        alt={`${dog.name}, a ${dog.size} rescue dog`}
        sizes={sizes}
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        className="h-full w-full object-cover"
      />
      {caption && (
        <span className="text-stone-neutral absolute right-2 bottom-2 rounded-full bg-white/85 px-2 py-0.5 text-[10px] font-medium backdrop-blur-sm">
          Representative photo
        </span>
      )}
    </div>
  )
}
