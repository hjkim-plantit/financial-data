import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import FundListPage from './pages/FundListPage'
import ImportReviewPage from './pages/ImportReviewPage'
import ImportDetailPage from './pages/ImportDetailPage'
import BankImportsPage from './pages/BankImportsPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<FundListPage />} />
        <Route path="/bank-imports" element={<BankImportsPage />} />
        <Route path="/imports" element={<ImportReviewPage />} />
        <Route path="/imports/:id" element={<ImportDetailPage />} />
      </Routes>
    </Layout>
  )
}
