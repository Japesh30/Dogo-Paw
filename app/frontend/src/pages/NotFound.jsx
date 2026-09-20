import { Link } from 'react-router-dom'
import DogAvatar from '../components/DogAvatar'

export default function NotFound() {
  return (
    <section className="shell grid min-h-[70vh] place-items-center py-20 text-center">
      <div className="flex flex-col items-center">
        <DogAvatar seed={1} className="rounded-card h-40 w-56" />
        <p className="eyebrow mt-6">404</p>
        <h1 className="mt-3 text-3xl sm:text-4xl">This page has wandered off</h1>
        <p className="mt-4 max-w-md text-balance">
          The link you followed does not exist. Head back home — the dogs are
          all still there.
        </p>
        <Link to="/" className="btn-primary mt-8">
          Back to home
        </Link>
      </div>
    </section>
  )
}
