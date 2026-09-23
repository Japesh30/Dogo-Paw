// Field definitions for the medical data-entry forms.
//
// Kept out of the component file so the module exports data only, which is
// what fast refresh expects.

/**
 * Field definitions per record type.
 *
 * These mirror the API so the form asks for the right things and marks what is
 * required — a convenience, not a validation layer. The rules that actually
 * decide whether a record is acceptable (dates that must agree, a completed
 * course needing an end date, plausible weights and temperatures) live in the
 * backend, and its message is what gets shown when it refuses.
 */
export const FORM_FIELDS = {
  records: [
    { name: 'title', label: 'Title', required: true, placeholder: 'Annual check-up' },
    {
      name: 'record_type',
      label: 'Type',
      required: true,
      options: ['checkup', 'treatment', 'surgery', 'diagnostic', 'emergency', 'dental', 'other'],
    },
    { name: 'visit_date', label: 'Visit date', type: 'date', required: true },
    { name: 'veterinarian', label: 'Veterinarian', placeholder: 'Dr. A. Rao' },
    { name: 'description', label: 'Notes', textarea: true, full: true },
  ],
  vaccinations: [
    { name: 'vaccine_name', label: 'Vaccine', required: true, placeholder: 'DHPP' },
    {
      name: 'status',
      label: 'Status',
      required: true,
      options: ['completed', 'scheduled', 'overdue'],
    },
    { name: 'administered_date', label: 'Administered', type: 'date' },
    { name: 'next_due_date', label: 'Next due', type: 'date' },
    { name: 'veterinarian', label: 'Veterinarian' },
    { name: 'notes', label: 'Notes', textarea: true, full: true },
  ],
  medications: [
    { name: 'medication_name', label: 'Medication', required: true },
    { name: 'dosage', label: 'Dosage', required: true, placeholder: '1 tablet' },
    { name: 'frequency', label: 'Frequency', required: true, placeholder: 'twice daily' },
    { name: 'start_date', label: 'Start date', type: 'date', required: true },
    { name: 'end_date', label: 'End date', type: 'date' },
    {
      name: 'status',
      label: 'Status',
      required: true,
      options: ['active', 'completed', 'discontinued'],
    },
    { name: 'prescribed_by', label: 'Prescribed by' },
    { name: 'notes', label: 'Notes', textarea: true, full: true },
  ],
  observations: [
    { name: 'observation_date', label: 'Date', type: 'date', required: true },
    { name: 'weight_kg', label: 'Weight (kg)', type: 'number', step: '0.1', numeric: true },
    {
      name: 'temperature_c',
      label: 'Temperature (°C)',
      type: 'number',
      step: '0.1',
      numeric: true,
    },
    {
      name: 'symptoms',
      label: 'Symptoms',
      placeholder: 'lethargy, reduced appetite',
      hint: 'Separate with commas',
      list: true,
      full: true,
    },
    { name: 'notes', label: 'Notes', textarea: true, full: true },
  ],
  'follow-ups': [
    { name: 'reason', label: 'Reason', required: true, placeholder: 'Recheck medication levels' },
    { name: 'due_date', label: 'Due date', type: 'date', required: true },
    {
      name: 'status',
      label: 'Status',
      required: true,
      options: ['pending', 'completed', 'missed', 'cancelled'],
    },
    { name: 'completed_date', label: 'Completed on', type: 'date' },
    { name: 'notes', label: 'Notes', textarea: true, full: true },
  ],
}
