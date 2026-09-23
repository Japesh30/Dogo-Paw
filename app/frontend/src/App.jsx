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
import AdminHealth from './pages/AdminHealth'
import AdminDogMedical from './pages/AdminDogMedical'
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
        {/* Medical data is admin-only. The guard here keeps it out of the UI;
            the backend refuses the requests regardless. */}
        <Route
          path="admin/health"
          element={
            <ProtectedRoute requireAdmin>
              <AdminHealth />
            </ProtectedRoute>
          }
        />
        <Route
          path="admin/health/dogs/:dogId"
          element={
            <ProtectedRoute requireAdmin>
              <AdminDogMedical />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
