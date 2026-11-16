import { Module } from '@nestjs/common';
import { FolhaController } from './folha.controller';
import { FolhaService } from './folha.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [AuthModule],
  controllers: [FolhaController],
  providers: [FolhaService],
  exports: [FolhaService],
})
export class FolhaModule {}

