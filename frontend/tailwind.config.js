/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        sap: {
          blue: '#0070F2',
          'blue-light': '#E1F4FF',
          'blue-dark': '#002A86',
          navy: '#354A5F',
          'navy-deep': '#00144A',
          gray: {
            50: '#F7F7F7',
            100: '#F5F6F7',
            200: '#EAECEE',
            300: '#E5E5E5',
            400: '#BCC3CA',
            500: '#6A6D70',
            600: '#32363A',
          }
        }
      },
      fontFamily: {
        sap: ['72', '72full', 'Arial', 'Helvetica', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
