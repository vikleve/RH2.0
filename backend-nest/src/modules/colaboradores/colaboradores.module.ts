import { Module } from '@nestjs/common';
import { ColaboradoresController } from './colaboradores.controller';
import { ColaboradoresService } from './colaboradores.service';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [AuthModule],
  controllers: [ColaboradoresController],
  providers: [ColaboradoresService],
  exports: [ColaboradoresService],
})
export class ColaboradoresModule {}

