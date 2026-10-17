const express = require('express');
const path = require('path');
const app = express();
app.use(express.json({ limit: '1mb' }));
app.use(express.static(path.join(__dirname, 'public'), { dotfiles: 'allow' }));

app.post('/api/chat', async (req, res) => {
  try {
    if (!process.env.GROQ_API_KEY) return res.status(500).json({ error: 'GROQ_API_KEY Render ortam değişkenlerine eklenmemiş.' });
    const { messages, model } = req.body;
    const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + process.env.GROQ_API_KEY },
      body: JSON.stringify({ model: model || 'llama-3.3-70b-versatile', messages, temperature: 0.7, max_tokens: 500 })
    });
    const d = await r.json();
    if (!r.ok) return res.status(r.status).json({ error: (d.error && d.error.message) || 'Groq hatası' });
    res.json({ reply: d.choices[0].message.content });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.listen(process.env.PORT || 3000, () => console.log('Katia çalışıyor'));
