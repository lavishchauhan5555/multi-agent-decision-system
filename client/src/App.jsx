import { useState } from 'react'

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'

import './App.css'

function App() {

  // const sendMessage = async () => {
  //   const res = await fetch("http://localhost:10000/api/chat", {
  //     method: "POST",
  //     headers: {
  //       "Content-Type": "application/json",
  //     },
  //     body: JSON.stringify({ message: "Hello AI" }),
  //   });

  //   const data = await res.json();
  //   console.log(data);
  // };
  return (
    <>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>

    </>
  )
}

export default App
