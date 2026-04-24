// config/db.js
import mongoose from "mongoose";

// const connectDB = async () => {
//   try {
//     const conn = await mongoose.connect(process.env.MONGO_URI,{dbName:"Debet-workflow"});

//     console.log(`MongoDB Connected: ${conn.connection.host}`);
//   } catch (error) {
//     console.error("DB connection error:", error.message);
//     process.exit(1);
//   }
// };


 
const connectDB = async () => {
  const uri = process.env.MONGO_URI;
 
  if (!uri) {
    console.warn('[DB] MONGODB_URI not set — skipping DB connection (Phase 5 dev mode)');
    return;
  }
 
  try {
    await mongoose.connect(uri, {
      serverSelectionTimeoutMS: 5000,
    });
    console.log('[DB] MongoDB connected');
  } catch (err) {
    console.error('[DB] Connection failed:', err.message);
    console.warn('[DB] Continuing without DB — session persistence disabled');
  }
};
 
mongoose.connection.on('disconnected', () => {
  console.warn('[DB] MongoDB disconnected');
});

export default connectDB;