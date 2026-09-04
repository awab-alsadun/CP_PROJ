import { useTranslation } from 'react-i18next'

export default function CompanyDocuments() {
  const { t } = useTranslation()
  return <div className="p-6">{t('companyDocumentsStub')}</div>
}
