// Single import surface for the artwork carried over from the original site.
// Filenames are unchanged from the old `assest/image` folder.
import logo from './images/logo.png'
import banner1 from './images/banner1.png'
import tommy from './images/tommy.jpg'
import vol1 from './images/vol1.jpg'
import vol2 from './images/vol2.jpg'
import vol3 from './images/vol3.jpg'
import foster1 from './images/foster1.jpg'
import foster2 from './images/foster2.jpg'
import foster3 from './images/foster3.jpg'
import foster4 from './images/foster4.jpg'
import foster5 from './images/foster5.jpg'
import foster6 from './images/foster6.jpg'
import dog2 from './images/dog2.png'
import dog3 from './images/dog3.png'
import dog5 from './images/dog5.png'

export { logo, banner1, tommy, dog2, dog3, dog5 }

export const volunteerPhotos = [
  { src: vol1, alt: 'A volunteer walking a rescue dog on a lead' },
  { src: vol2, alt: 'Volunteers greeting a dog at an adoption event' },
  { src: vol3, alt: 'A volunteer sitting with a dog waiting for a home' },
]

export const fosterPhotos = [
  { src: foster1, alt: 'A foster dog settling in on a living-room rug' },
  { src: foster2, alt: 'A foster dog resting beside its temporary family' },
  { src: foster3, alt: 'A puppy playing in a foster home garden' },
  { src: foster4, alt: 'A foster carer feeding a rescue dog' },
  { src: foster5, alt: 'A rescue dog curled up asleep in its foster bed' },
  { src: foster6, alt: 'A foster dog out on a walk with its carer' },
]

// The hero video lives in /public so Vite never tries to inline 28 MB of MP4.
export const heroVideo = '/media/video-1.mp4'
