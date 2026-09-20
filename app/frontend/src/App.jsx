import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Home from './pages/Home'
import About from './pages/About'
import Volunteer from './pages/Volunteer'
import Foster from './pages/Foster'
import Dogs from './pages/Dogs'
import DogProfile from './pages/DogProfile'
import Login from './pages/Login'
import AdoptMatch from './pages/AdoptMatch'
import Admin from './pages/Admin'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="about" element={<About />} />
        <Route path="volunteer" element={<Volunteer />} />
        <Route path="foster" element={<Foster />} />
        <Route path="dogs" element={<Dogs />} />
        <Route path="dogs/:dogId" element={<DogProfile />} />
        <Route path="login" element={<Login />} />
        <Route path="adopt-match" element={<AdoptMatch />} />
        <Route
          path="admin"
          element={
            <ProtectedRoute requireAdmin>
              <Admin />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
